# Hướng dẫn cấu hình đăng nhập Microsoft Entra ID

## 1. Tạo App registration trong Entra

1. Entra admin center → App registrations → New registration.
2. Supported account types: **Single tenant only** (chỉ tenant của bạn).
3. Redirect URI: nền tảng **Web**, giá trị `https://<host>/auth/entra/callback` (KHÔNG có dấu `/` cuối). Nếu board công khai (space) chạy ở host khác, thêm Redirect URI thứ hai `https://<space-host>/auth/entra/callback`.
4. API permissions → Microsoft Graph → Delegated → `User.Read` (kèm openid, email, profile mặc định). Grant admin consent nếu tenant yêu cầu.
5. Certificates & secrets → New client secret. Ghi lại **Value** ngay (chỉ hiện một lần) và **ngày hết hạn** để gia hạn trước hạn.
6. (Khuyến nghị) Token configuration → Add optional claim → ID → `email`.
7. Ghi lại Directory (tenant) ID và Application (client) ID ở trang Overview.

## 2. Điền God Mode

God Mode → Authentication → Microsoft Entra ID:

| Trường                | Giá trị                                                                   |
| --------------------- | ------------------------------------------------------------------------- |
| Tenant ID             | GUID của tenant (không dùng `common`/`organizations`)                     |
| Client ID             | Application (client) ID                                                   |
| Client Secret         | Value của secret                                                          |
| Button label          | Nhãn nút đăng nhập (mặc định "Microsoft")                                 |
| Allowed email domains | Danh sách domain cho phép, phân tách bằng dấu phẩy; để trống = mọi domain |
| Sync                  | Bật để cập nhật tên/ảnh từ Entra mỗi lần đăng nhập                        |
| SSO-only              | Ẩn form email/mật khẩu ở trang đăng nhập chính                            |

**Cảnh báo SSO-only:** khi bật, đăng nhập email/mật khẩu chuyển sang `/login/internal`. Hãy kiểm tra đăng nhập Entra chạy được ở một cửa sổ ẩn danh, và giữ sẵn một tài khoản admin có mật khẩu (qua `/login/internal`) trước khi bật, kẻo khóa mình ngoài hệ thống.

## 3. Hành vi cần biết

- Định danh người dùng = claim `oid` (không phải email).
- Tenant bị ghim theo Tenant ID đã cấu hình; token từ tenant khác (guest) bị từ chối.
- Email lấy từ token (`email`, sau đó `preferred_username`): hãy bật optional claim `email` hoặc đảm bảo user có `mail`.
- Tên hiển thị = claim `name`; ảnh lấy qua Graph (`/me/photo`), không có ảnh thì dùng mặc định.
- `ENABLE_SIGNUP` vẫn áp dụng: nếu tắt, người chưa có tài khoản Plane không tự tạo được qua Entra.
- Đăng xuất khỏi Plane KHÔNG đăng xuất khỏi Microsoft.

**Lưu ý về claim `email`:** Entra không đảm bảo `email` đã được xác minh hoặc bất biến (Microsoft khuyến cáo không dùng nó để phân quyền). Plane chỉ dùng `email` để tạo/khớp tài khoản, còn danh tính luôn là `oid`. Vì chỉ ghim một tenant, rủi ro giới hạn ở những người dùng tự sửa được thuộc tính mail của mình. Giảm thiểu: đặt `ENTRA_ALLOWED_EMAIL_DOMAINS`, hạn chế ai được sửa `mail` trong Entra, và có thể dùng optional claim `xms_edov` trong thay đổi sau.

## 4. Xử lý lỗi

| Mã                          | Ý nghĩa                                                                                                             | Cách xử lý                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| 5126 `ENTRA_NOT_CONFIGURED` | Thiếu Tenant ID/Client ID/Secret hoặc chưa bật                                                                      | Kiểm tra God Mode                                                    |
| 5127 `ENTRA_PROVIDER_ERROR` | Lỗi từ Entra: sai secret/hết hạn, sai redirect URI, state/nonce/tenant không khớp, thiếu `oid`, hoặc người dùng hủy | Kiểm tra secret còn hạn, Redirect URI khớp tuyệt đối, đúng tenant    |
| 5128 `ENTRA_EMAIL_UNUSABLE` | Token không có email hợp lệ, hoặc email ngoài `ENTRA_ALLOWED_EMAIL_DOMAINS`                                         | Thêm optional claim `email` / điền `mail`, hoặc sửa danh sách domain |

## 5. Checklist kiểm thử thủ công (tenant thật)

- [ ] Đăng nhập lần đầu: tạo tài khoản mới, có tên (`name`) và ảnh nếu tài khoản Entra có ảnh.
- [ ] Đăng nhập lần hai: vào đúng tài khoản cũ, không tạo trùng.
- [ ] Tài khoản Plane có sẵn cùng email: đăng nhập vào chính tài khoản đó.
- [ ] Tài khoản Entra không có ảnh: đăng nhập bình thường, dùng avatar mặc định.
- [ ] Người dùng ngoài `ENTRA_ALLOWED_EMAIL_DOMAINS`: bị từ chối (5128).
- [ ] Guest / người dùng tenant khác: bị từ chối.
- [ ] `ENABLE_SIGNUP=0`: người chưa có tài khoản bị từ chối; người đã có vẫn đăng nhập được.
- [ ] SSO-only, chỉ một provider bật: trang đăng nhập tự chuyển sang Entra.
- [ ] SSO-only, có lỗi: hiện các nút đăng nhập, không bị lặp chuyển hướng.
- [ ] SSO-only, đã đăng xuất: `/login/internal` truy cập được.
- [ ] SSO-only: đăng xuất không bị đẩy ngược đăng nhập lại ngay.
- [ ] Không provider nào bật: trang đăng nhập hiện form email.
- [ ] Space board: đăng nhập từ board sẽ quay lại đúng board.

## Bảo mật liên kết tài khoản (sau review)

- Danh tính là `oid`. Nếu `oid` đã gắn với một tài khoản Plane mà email trong Entra thay đổi → từ chối đăng nhập (lỗi 5128), không tự chuyển sang tài khoản khác.
- Email đã tồn tại trong Plane (tài khoản local/provider khác) chỉ được liên kết lần đầu khi **`ENTRA_ALLOWED_EMAIL_DOMAINS` đã được đặt** (God Mode → Allowed email domains). Nếu để trống, đăng nhập bị từ chối (5128) để tránh chiếm tài khoản qua claim email có thể sửa được.
- Tài khoản khách B2B (`idp` hoặc `#EXT#`) bị từ chối.
- Khi chạy sau proxy/CDN: proxy phải giữ nguyên `Host` và gửi `X-Forwarded-Proto: https`, nếu không `redirect_uri` sai và Entra báo AADSTS50011. Space ở host khác cũng phải proxy `/auth/*` về API; `APP_BASE_URL`, `SPACE_BASE_URL`, `WEB_URL` phải đúng.
- Khi SSO-only bị lỗi: dùng `/login/internal` hoặc `/?no_redirect=1` để dừng tự chuyển hướng. Trang space không áp dụng SSO-only.
- Biến cấu hình (God Mode ghi đè env): `IS_ENTRA_ENABLED`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` (mã hóa), `ENTRA_PROVIDER_NAME`, `ENTRA_ALLOWED_EMAIL_DOMAINS`, `ENABLE_ENTRA_SYNC`, `SSO_ONLY_LOGIN_PAGE`.
