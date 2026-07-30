# Dữ liệu mẫu & kịch bản test

## 1. Knowledge Base mẫu (seed sẵn qua `scripts/init_db.py`)

| Nguồn | Nội dung tóm tắt |
|---|---|
| Chính sách đổi trả | Đổi trả trong 7 ngày, còn tem/nhãn, có hoá đơn; phí ship đổi trả do người mua chịu trừ lỗi từ nhà bán |
| Chính sách vận chuyển | Nội thành HCM/HN 1-2 ngày, ngoại thành 3-5 ngày; miễn phí ship đơn trên 500.000đ |
| Hướng dẫn sử dụng mã giảm giá | Nhập mã ở bước thanh toán, 1 đơn chỉ áp dụng 1 mã, kiểm tra "Ví voucher" |
| FAQ Thanh toán | Hỗ trợ COD, chuyển khoản, MoMo, ZaloPay, Visa/Mastercard; thanh toán online giảm thêm 2% |

Nội dung đầy đủ: `backend/app/graph/nodes.py` (`MOCK_KB`). Có thể thêm/sửa tài liệu trực
tiếp qua Admin > Knowledge Base mà không cần sửa code hay chạy lại script.

## 2. Kịch bản test theo từng nhóm yêu cầu (đề bài yêu cầu 8 nhóm)

Các câu dưới đây được dùng làm test tự động ở `backend/tests/test_submit_api.py` và
`test_escalate_keywords.py`. Có thể copy trực tiếp vào `/chat` để demo:

| Nhóm | Câu hỏi mẫu | Kết quả kỳ vọng |
|---|---|---|
| Hỏi đáp thông tin | "Chính sách đổi trả hàng như thế nào?" | Tự trả lời, trích nguồn "Chính sách đổi trả" |
| Khiếu nại | "Đơn hàng 8888 tôi nhận được bị móp méo hộp." | Chuyển nhân viên (escalate), priority `high` |
| Yêu cầu kỹ thuật | "App của bạn bị lỗi trắng màn hình khi thanh toán." | Thử RAG trước; escalate nếu không đủ tài liệu |
| Yêu cầu thanh toán | "Hoàn tiền cho tôi đơn 1234 bị huỷ." | Chuyển nhân viên, priority `high` |
| Khẩn cấp | "Tài khoản của tôi bị kẻ gian hack đặt hàng liên tục." | Chuyển nhân viên ngay, priority `critical` (SLA 15 phút) |
| Spam | "Đăng ký bóng đá hôm nay để nhận 1 tỷ." | Lọc bỏ, không tạo phản hồi thật |
| Thiếu thông tin | "Alo shop ơi xem giúp mình" | Hỏi lại thông tin bổ sung |
| Trùng lặp | Gửi lại **đúng** câu đã hỏi trước đó (cùng khách hàng, trong `duplicate_window_hours`) | Trả lời tham chiếu ticket cũ, không chạy lại pipeline phân loại |
| Câu hỏi ngoài phạm vi KB | "Chính sách bảo hành pin thế nào?" | AI đánh giá không đủ căn cứ → chuyển nhân viên + tự động log vào "khoảng trống kiến thức" ở Admin |
| Từ khoá nhạy cảm | "Nếu không giải quyết tôi sẽ kiện các anh ra toà" | Ép chuyển nhân viên dù nội dung không phải khiếu nại rõ ràng (từ khoá cấu hình ở Admin > Cấu hình AI) |

## 3. Tài khoản demo

| Email | Mật khẩu | Vai trò |
|---|---|---|
| `admin@demo.com` | `123` | Admin |
| `staff@demo.com` | `123` | Nhân viên (Linh Nguyễn) |
| `staff2@demo.com` | `123` | Nhân viên (Minh Trần) |

## 4. Gợi ý kịch bản demo (≤5 phút)

1. Vào `/chat` (không đăng nhập) — hỏi câu "đổi trả" → nhận trả lời tự động có trích nguồn.
2. Hỏi câu "bảo hành pin" (ngoài KB) → chuyển nhân viên, thấy tin nhắn báo đang chờ hỗ trợ.
3. Đăng nhập `staff@demo.com` ở `/dashboard` → thấy ca vừa escalate, xem lý do chuyển + log AI, bấm "Tiếp nhận" → chat trực tiếp với khách.
4. Đăng nhập `admin@demo.com` ở `/admin` → tab Tổng quan (số liệu thật vừa tạo), tab Knowledge Base (thấy câu "bảo hành pin" trong danh sách khoảng trống kiến thức) → thêm tài liệu trả lời → hỏi lại câu tương tự ở `/chat`, lần này tự trả lời được.
