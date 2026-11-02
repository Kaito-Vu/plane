# OIDC / Microsoft Entra ID SSO (plugin) — Design

Ngày: 2026-10-28 · Trạng thái: **chờ duyệt** · Mục "Quyết định của tôi" (§8) là phần tôi tự chọn, chưa được bạn xác nhận.

## 1. Mục đích
Cho người dùng đăng nhập/đăng ký Plane bằng tài khoản Microsoft Entra ID của công ty. **Một tenant duy nhất** (đã chốt). Làm dưới dạng plugin trong khung EE của fork, core chỉ thêm điểm nối nhỏ.

## 2. Phạm vi
### Goals
- Đăng nhập Authorization Code + PKCE + `nonce` với một tenant Entra; hỗ trợ cả luồng app và space (như Gitea).
- Cấu hình ở God Mode (Client ID, Client Secret, Tenant ID, bật/tắt), lưu trong instance configuration, có fallback biến môi trường.
- Provider viết theo kiểu **OIDC chung** (issuer + discovery); Entra chỉ là cách dựng issuer từ Tenant ID → sau này thêm IdP OIDC khác không cần viết lại.
### Non-goals
- Multi-tenant, guest/B2B, SCIM, đồng bộ nhóm/vai trò, single logout, refresh token để gọi Microsoft Graph.
### Anti-goals
- Đăng nhập được bằng token của tenant khác hoặc token sai `aud`/`nonce`.
- Chiếm được tài khoản Plane có sẵn qua email không đáng tin.

## 3. Cách hoạt động (backend, `apps/api/plane/ee/oidc_auth/`)
- `provider.py`: `OIDCProvider(OauthAdapter)`, `provider = "entra"` (lớp con `EntraProvider`). Issuer = `https://login.microsoftonline.com/{TENANT_ID}/v2.0`. Lấy `authorization_endpoint`, `token_endpoint`, `jwks_uri` từ `{issuer}/.well-known/openid-configuration` (cache ngắn). Scope `openid email profile User.Read` (`User.Read` để lấy ảnh đại diện, xem §3c).
- Đổi code lấy token, **xác thực `id_token` bằng PyJWT** (đã có trong `pyproject.toml`, kèm `cryptography`): chữ ký qua JWKS, `iss` == issuer, `aud` == Client ID, `exp`, `nonce` khớp session. Thông tin user lấy từ chính id_token, không gọi thêm userinfo.
- `provider_id = oid` (định danh bất biến của Entra), `tid` phải bằng Tenant ID đã cấu hình.
- **Tên hiển thị = claim `name`** (cần scope `profile`). Theo tài liệu Microsoft (ID token claims reference), `name` là giá trị dễ đọc cho người, không đảm bảo duy nhất, có thể đổi, chỉ dùng để hiển thị. Plane đưa nguyên giá trị này vào `first_name`, `last_name` để trống (giống cách Gitea xử lý `full_name`); không tách họ/tên và không dùng `given_name`/`family_name` (đó là optional claim, mặc định không có).
- Email: Microsoft ghi rõ claim `email` **không đảm bảo đúng, có thể đổi, "never use it for authorization"**, và với user nội bộ chỉ có khi cấu hình optional claim `email` hoặc scope `email` v2.0. `preferred_username` cũng mutable và có thể không phải email. Plane vẫn cần một email để tạo tài khoản, nên: dùng claim `email` (scope `email`), nếu thiếu thì dùng `preferred_username` chỉ khi nó có dạng email, nếu không thì từ chối đăng nhập với lỗi rõ ràng. Email chỉ để tạo/khớp tài khoản Plane, **định danh vẫn là `oid`**. Rủi ro còn lại: admin tenant hoặc người dùng sửa được thuộc tính `mail` có thể trùng email người khác để chiếm tài khoản Plane có sẵn; chấp nhận được trong một tenant do công ty tự quản, và có tùy chọn danh sách domain email cho phép (§8).
- Dựa vào `complete_login_or_signup` hiện có của core: tự khớp tài khoản theo email, tôn trọng `ENABLE_SIGNUP`.
- View/URL: `/auth/entra/` + `/auth/entra/callback` cho app và space, sao chép khuôn `views/app/gitea.py`, `views/space/gitea.py` (dùng lại `validate_oauth_state`, `validate_next_path`, `user_login`).

## 3b. Trang đăng nhập (web và space) — theo yêu cầu của bạn
Hiện `/` chính là trang đăng nhập (`apps/web/app/(home)/page.tsx` → `AuthBase` → `auth-root.tsx`), hiển thị nút OAuth cùng form email/mật khẩu; `/login` hiện chỉ redirect về `/`.
- **Trang chính `/`** chỉ hiển thị các nút provider (không có form email/mật khẩu, không có magic code).
- **`/login/internal`** (route mới) hiển thị form email/mật khẩu và magic code như hiện nay, kể cả đăng ký.
- **Chỉ có đúng 1 provider bật → tự redirect** thẳng sang `/auth/<provider>/` (giữ `next_path`). Các trường hợp **không** redirect tự động, để tránh vòng lặp và khóa người dùng: URL có `error_code` (đăng nhập vừa lỗi, phải hiện thông báo lỗi và nút bấm tay), vừa đăng xuất, hoặc `?no_redirect=1`.
- **Không có provider nào bật** → trang chính hiển thị form email/mật khẩu như cũ (không để instance bị khóa).
- Lỗi của luồng email/mật khẩu (`AUTHENTICATION_FAILED_*`, mã magic code) hiện đang redirect về `/?error_code=…`; cần chuyển hướng về `/login/internal?…` để lỗi hiển thị đúng chỗ. **Cần xác minh khi lập plan** (ở backend là `views/app/email.py`, `magic.py`).
- Chức năng này bật/tắt bằng một cờ God Mode `SSO_ONLY_LOGIN_PAGE`, **mặc định tắt** để không đổi hành vi của core khi chưa bật OIDC.
- **Nút đăng nhập tùy biến theo tên provider:** admin nhập "tên provider" (ví dụ `Microsoft ETC`), lưu ở `ENTRA_PROVIDER_NAME`, trả về frontend qua `entra_provider_name`. Chữ trên nút lấy từ khóa i18n, ví dụ vi: `Đăng nhập qua {name}`, en: `Sign in with {name}` (theo skill `translate`, thêm khóa vào `packages/i18n`). Để trống thì mặc định `Microsoft`.

## 3c. Ảnh đại diện (avatar)
- **Entra không đưa ảnh vào `id_token`** (không có claim `picture`, xem bảng claim của Microsoft). Ảnh lấy qua Microsoft Graph: `GET https://graph.microsoft.com/v1.0/me/photo/$value` với access token của chính người dùng (scope `User.Read`, delegated). Trả `200` + dữ liệu ảnh nhị phân, hoặc **`404` nếu người dùng chưa có ảnh** (trường hợp phổ biến, không phải lỗi).
- **Dùng lại cơ chế avatar của core**: `download_and_upload_avatar` tải ảnh, kiểm tra loại/dung lượng, đẩy lên storage, tạo `FileAsset`. Lần đăng nhập đầu (tạo tài khoản) tự lấy ảnh; với người dùng cũ chỉ cập nhật khi bật `ENABLE_ENTRA_SYNC` (cơ chế sync sẵn có của core cho Google/GitHub/GitLab/Gitea).
- **Vấn đề bảo mật cần xử lý:** hàm tải ảnh của core gửi `headers` ở **mọi bước redirect**, kể cả sang host khác, nên nếu chỉ truyền Bearer token qua `get_avatar_download_headers()` thì token Graph có thể bị gửi tới host lạ khi gặp redirect. Cách làm: thêm một điểm nối nhỏ ở `adapter/base.py` (tách bước "tải ảnh" thành một method `fetch_avatar` mà provider ghi đè được); `EntraProvider` ghi đè để chỉ gọi đúng `graph.microsoft.com` (`allowed_hosts`), không theo redirect sang host khác.
- **Ảnh không được làm hỏng đăng nhập:** `404`, `403`, timeout, throttling hay ảnh quá lớn/sai định dạng → bỏ qua, đăng nhập vẫn thành công, người dùng có avatar mặc định.
- **Không để lại URL chết:** core lưu URL gốc vào `user.avatar` làm phương án dự phòng khi tải thất bại; URL Graph cần token nên vô dụng với trình duyệt. `EntraProvider` xóa giá trị này khi không có `avatar_asset`.
- **Sync không được xóa nhầm ảnh cũ:** `sync_user_data` của core xóa avatar cũ trước khi tải ảnh mới, nên nếu Graph trả `404` thì người dùng mất ảnh đang có. `EntraProvider` ghi đè: không có ảnh trên Entra thì giữ nguyên ảnh cũ.
- Quyền: `User.Read` (delegated) thường đã có sẵn khi tạo app registration và người dùng tự đồng ý được; chỉ cần kiểm tra nó có trong **API permissions**.

## 4. Điểm nối vào core (cần allowlist, xác minh từng chỗ khi lập plan)
1. `authentication/urls.py`: include URL của plugin.
2. `authentication/adapter/error.py`: `ENTRA_NOT_CONFIGURED`, `ENTRA_PROVIDER_ERROR`.
3. `utils/instance_config_variables/core.py` và `license/api/views/instance.py`: `IS_ENTRA_ENABLED`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `is_entra_enabled` trả về frontend.
4. `adapter/base.py`: thêm `entra` → `ENABLE_ENTRA_SYNC` vào `provider_config_map` trong `check_sync_enabled`, và tách `fetch_avatar` để provider ghi đè (§3c). Thêm khóa `ENABLE_ENTRA_SYNC` vào instance config.
5. Frontend web/space: `app/(home)/page.tsx` và `components/account/auth-forms/auth-root.tsx` (ẩn form email, tự redirect), route mới `login/internal` (qua `app/routes/extended`), `hooks/oauth/core.tsx` (nút OIDC với `entra_provider_name`), khóa i18n.
6. Frontend: `apps/admin` (route, trang cấu hình, `hooks/oauth`, header), `apps/web` và `apps/space` (`hooks/oauth/core.tsx`), `packages/constants/src/auth`, `packages/types/src/instance`.

## 5. Bảo mật
- Từ chối nếu `tid` ≠ Tenant ID, `aud` sai, `nonce`/`state` sai, token hết hạn, thuật toán không phải RS256.
- Client Secret lưu như các secret khác trong instance configuration (đã mã hóa theo cơ chế core); không ghi vào log.
- Không gọi URL tùy ý do người dùng nhập: chỉ host `login.microsoftonline.com`, Tenant ID phải đúng dạng GUID (tránh SSRF, xem `test_ssrf_advisories.py`).
- Email lấy từ tenant đã khóa, nên rủi ro "nOAuth" của app multi-tenant không áp dụng; vẫn ghi lại là điều kiện: **không bao giờ mở rộng sang multi-tenant mà không thêm kiểm tra domain/`oid`**.

## 6. Kiểm thử
- Unit: xác thực id_token (hợp lệ, sai `iss`, sai `aud`, sai `tid`, hết hạn, sai `nonce`, thiếu email), dựng issuer từ Tenant ID, từ chối Tenant ID sai định dạng.
- Contract: callback app và space theo mẫu `test_oauth_callback_state_app.py` (state sai, thiếu code, đăng nhập thành công, `ENABLE_SIGNUP=0`).
- Thủ công: một tenant Entra thật (đăng nhập, đăng ký lần đầu, tài khoản có sẵn cùng email).

## 7. Thứ tự làm
1. Khung EE (dùng chung với work-item-types; phụ thuộc đầu tiên).
2. Provider + view/URL + test backend.
3. Điểm nối core.
4. Trang admin.
5. Nút đăng nhập web/space.
6. Chạy thử với tenant thật.

## 8. Đã chốt và quyết định của tôi
**Bạn đã chốt:** (1) đăng nhập email/mật khẩu vẫn còn nhưng ở `/login/internal`, trang chính chỉ có provider, 1 provider thì tự redirect; (2) tự tạo tài khoản ở lần đăng nhập đầu; (3) định danh bằng `oid`; (4) tên hiển thị theo display name của Azure; (5) tên nút tùy biến theo tên provider do admin nhập.

**Mình tự chọn, cần bạn kiểm tra:**
- Cờ `SSO_ONLY_LOGIN_PAGE` (mặc định tắt) để bật hành vi §3b, thay vì áp cho mọi instance.
- "Display name" = claim `name` (xem §3), không tách họ/tên.
- Từ chối đăng nhập nếu không có email hợp lệ trong token.
- Tùy chọn `ENTRA_ALLOWED_EMAIL_DOMAINS` (danh sách, để trống = không giới hạn): chỉ chấp nhận email thuộc domain này. Mình đề xuất bật khi tenant có nhiều domain/alias.
- "Tự tạo tài khoản" vẫn tuân theo `ENABLE_SIGNUP` của instance; nếu `ENABLE_SIGNUP=0` thì người chưa có lời mời sẽ bị chặn như các provider khác.
- `ENABLE_ENTRA_SYNC` mặc định tắt: tắt thì người dùng cũ không bị cập nhật tên/ảnh mỗi lần đăng nhập; ảnh của người dùng mới vẫn được lấy.
- Tên provider/URL/cấu hình là `entra` (theo yêu cầu của bạn); logic OIDC chung nằm ở lớp cơ sở `OIDCProvider`, `EntraProvider` chỉ dựng issuer từ Tenant ID, để sau này thêm IdP OIDC khác chỉ cần lớp con mới.

## 9. Việc cần bạn cung cấp khi làm thật
Tenant ID, Client ID, Client Secret của app registration (kèm quyền Graph `User.Read` trong API permissions), và Redirect URI `https://<host>/auth/entra/callback` (thêm cả host của space nếu khác).

## 10. Callback URL
- Redirect URI đăng ký trong Entra và gửi trong request: `https://<host>/auth/entra/callback` (**không có dấu `/` cuối**, theo yêu cầu của bạn). Core hiện dùng dạng có `/` cuối (`/auth/gitea/callback/`), nên URL pattern của plugin chấp nhận cả hai (`callback/?`) nhưng `redirect_uri` gửi đi luôn là dạng không có `/`; Entra so khớp **chính xác từng ký tự**, nên phải đăng ký đúng chuỗi này.
- Bắt đầu đăng nhập: `/auth/entra/`. Space dùng cùng đường dẫn trên host của space (đăng ký thêm redirect URI cho host đó nếu khác).
