class AppError(Exception):
    def __init__(self, status, code, message):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


def require(
    condition, status=403, code="forbidden", message="Bạn không có quyền thực hiện thao tác này."
):
    if not condition:
        raise AppError(status, code, message)
