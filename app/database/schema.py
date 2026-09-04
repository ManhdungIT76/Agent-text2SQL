# Định nghĩa cấu trúc các bảng PostgreSQL cho mảng Bán lẻ

RETAIL_DATABASE_SCHEMA = """  + Bảng customer: customer_id (int), first_name (varchar), last_name (varchar), email (varchar), active (int: 1-hoạt động, 0-khóa).
  + Bảng film: film_id (int), title (varchar), release_year (int), rental_rate (numeric), length (int).
  + Bảng payment: payment_id (int), customer_id (int), amount (numeric), payment_date (timestamp)."""
