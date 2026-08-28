from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = 409
    default_detail = "Conflict."
    default_code = "conflict"


class Unprocessable(APIException):
    status_code = 422
    default_detail = "Unprocessable entity."
    default_code = "unprocessable_entity"
