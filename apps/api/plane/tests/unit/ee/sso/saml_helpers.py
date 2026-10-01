# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import base64
import datetime
import uuid
from datetime import timedelta, timezone
from xml.sax.saxutils import escape

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from onelogin.saml2.constants import OneLogin_Saml2_Constants as C
from onelogin.saml2.utils import OneLogin_Saml2_Utils

_FMT = "%Y-%m-%dT%H:%M:%SZ"


def make_cert_and_key():
    """Return (private_key_pem, certificate_pem) as str for a throwaway self-signed IdP cert."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-idp")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return key_pem, cert.public_bytes(serialization.Encoding.PEM).decode()


def build_saml_response(
    *,
    acs_url,
    idp_entity_id,
    sp_entity_id,
    in_response_to,
    name_id,
    key_pem,
    cert_pem,
    attrs=None,
    assertion_id=None,
    valid_for=300,
    sign=True,
    name_id_format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
):
    def esc(v):  # values go into XML text and attributes
        return escape(str(v), {'"': "&quot;"})

    irt_attr = f' InResponseTo="{esc(in_response_to)}"' if in_response_to else ""
    acs_url, idp_entity_id, sp_entity_id, name_id, name_id_format = (
        esc(v) for v in (acs_url, idp_entity_id, sp_entity_id, name_id, name_id_format)
    )
    now = datetime.datetime.now(timezone.utc)
    issued = now.strftime(_FMT)
    not_before = (now - timedelta(minutes=1)).strftime(_FMT)
    not_after = (now + timedelta(seconds=valid_for)).strftime(_FMT)
    assertion_id = assertion_id or f"_a{uuid.uuid4().hex}"
    attrs = attrs if attrs is not None else {"firstName": "An", "lastName": "Nguyen"}
    attribute_xml = "".join(
        f'<saml:Attribute Name="{esc(name)}"><saml:AttributeValue xsi:type="xs:string">{esc(value)}</saml:AttributeValue></saml:Attribute>'
        for name, value in attrs.items()
    )
    xml = (
        '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
        ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
        ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        f' ID="_r{uuid.uuid4().hex}" Version="2.0" IssueInstant="{issued}"'
        f' Destination="{acs_url}"{irt_attr}>'
        f"<saml:Issuer>{idp_entity_id}</saml:Issuer>"
        '<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f'<saml:Assertion ID="{assertion_id}" Version="2.0" IssueInstant="{issued}">'
        f"<saml:Issuer>{idp_entity_id}</saml:Issuer>"
        "<saml:Subject>"
        f'<saml:NameID Format="{name_id_format}">{name_id}</saml:NameID>'
        '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData NotOnOrAfter="{not_after}" Recipient="{acs_url}"{irt_attr}/>'
        "</saml:SubjectConfirmation></saml:Subject>"
        f'<saml:Conditions NotBefore="{not_before}" NotOnOrAfter="{not_after}">'
        f"<saml:AudienceRestriction><saml:Audience>{sp_entity_id}</saml:Audience></saml:AudienceRestriction>"
        "</saml:Conditions>"
        f'<saml:AuthnStatement AuthnInstant="{issued}" SessionIndex="_s1"><saml:AuthnContext>'
        "<saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef>"
        "</saml:AuthnContext></saml:AuthnStatement>"
        f"<saml:AttributeStatement>{attribute_xml}</saml:AttributeStatement>"
        "</saml:Assertion></samlp:Response>"
    )
    if sign:
        # explicit SHA-256: settings use rejectDeprecatedAlgorithm, and add_sign's default differs by version
        signed = OneLogin_Saml2_Utils.add_sign(xml, key_pem, cert_pem, sign_algorithm=C.RSA_SHA256, digest_algorithm=C.SHA256)
        xml = signed.decode() if isinstance(signed, bytes) else signed
    return base64.b64encode(xml.encode()).decode()
