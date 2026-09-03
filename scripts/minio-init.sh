#!/bin/sh
set -e

until mc alias set minio "http://minio:9000" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" 2>/dev/null; do
  echo "minio-init: waiting for minio"
  sleep 2
done

mc mb "minio/${S3_BUCKET_NAME}" --ignore-existing

cat > /tmp/app-bucket-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": ["s3:*"],
      "Effect": "Allow",
      "Resource": [
        "arn:aws:s3:::${S3_BUCKET_NAME}",
        "arn:aws:s3:::${S3_BUCKET_NAME}/*"
      ]
    }
  ]
}
EOF

mc admin policy create minio app-bucket-policy /tmp/app-bucket-policy.json || true
mc admin user add minio "${APP_S3_ACCESS_KEY}" "${APP_S3_SECRET_KEY}" || true
mc admin policy attach minio app-bucket-policy --user "${APP_S3_ACCESS_KEY}" || true

echo "minio-init: bucket ${S3_BUCKET_NAME} ready"
