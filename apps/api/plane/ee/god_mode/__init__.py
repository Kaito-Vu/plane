"""God-mode plugin: superadmin gate, workspace delete/archive, admin-access management.

Everything lives under plane.ee; core is left untouched. Hooks into core:
  * URLs in plane.ee.urls (included ahead of plane.license.urls) shadow/extend /api/instances/...
  * apps.EeConfig.ready() calls ``access.install()`` to tighten core's InstanceAdminPermission.
"""
