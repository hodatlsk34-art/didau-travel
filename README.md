# Đi Đâu? – AI Travel Planner Việt Nam

Web app tĩnh (một file `public/index.html`). Triển khai trên Render dạng Static Site, thư mục xuất bản: `public`.

- Bản đồ: Leaflet + OpenStreetMap; ranh giới 34 tỉnh thành từ dự án vietnam-map-34-provinces (MIT).
- Dữ liệu địa điểm là dữ liệu mẫu, cần xác minh trước khi dùng thật.
- Mã đối tác (affiliate): sửa hằng số `AFF` trong `public/index.html`.

## Viết bài Blog (trang quản trị)

- Vào https://didautravel.id.vn/admin/ → **Sign In Using Access Token** → dán mã truy cập GitHub (fine-grained token, chỉ repo `didau-travel`, quyền **Contents: Read and write**).
- Mỗi bài là một file trong `content/blog/`. Bấm **Save** → GitHub Action "Tạo trang Blog" tự tạo trang, sitemap, thu nhỏ ảnh tải lên, rồi Render tự cập nhật web (Auto-Deploy khi có commit). Có thể thêm khóa bí mật `RENDER_DEPLOY_HOOK` làm dự phòng.
- Chèn nút lịch trình giữa bài: một dòng riêng `[[dest:Tỉnh|Điểm đến|Chữ trên nút]]`.
