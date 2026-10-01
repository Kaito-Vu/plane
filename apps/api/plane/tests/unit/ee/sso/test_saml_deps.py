# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest


@pytest.mark.unit
def test_saml_stack_imports_and_xmlsec_sign_verify_roundtrip():
    import xmlsec
    from lxml import etree
    from onelogin.saml2.auth import OneLogin_Saml2_Auth  # noqa: F401
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    from plane.tests.unit.ee.sso.saml_helpers import make_cert_and_key

    key_pem, cert_pem = make_cert_and_key()
    from onelogin.saml2.constants import OneLogin_Saml2_Constants as C

    xml = (
        '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
        ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_1" Version="2.0">'
        "<saml:Issuer>x</saml:Issuer></samlp:Response>"
    )
    signed = OneLogin_Saml2_Utils.add_sign(
        xml, key_pem, cert_pem, sign_algorithm=C.RSA_SHA256, digest_algorithm=C.SHA256
    )
    root = etree.fromstring(signed)
    sig = xmlsec.tree.find_node(root, xmlsec.constants.NodeSignature)
    ctx = xmlsec.SignatureContext()
    ctx.key = xmlsec.Key.from_memory(cert_pem, xmlsec.constants.KeyDataFormatCertPem)
    xmlsec.tree.add_ids(root, ["ID"])
    ctx.verify(sig)  # raises on failure
