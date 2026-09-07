import os
import boto3
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv()

CF_R2_ACCESS_KEY = os.getenv("CF_R2_ACCESS_KEY_ID")
CF_R2_SECRET_KEY = os.getenv("CF_R2_SECRET_ACCESS_KEY")
CF_R2_ENDPOINT_URL = os.getenv("CF_R2_ENDPOINT_URL")
BUCKET_NAME = os.getenv("CF_R2_BUCKET_NAME")

client = boto3.client(
    "s3",
    endpoint_url=CF_R2_ENDPOINT_URL,
    aws_access_key_id=CF_R2_ACCESS_KEY,
    aws_secret_access_key=CF_R2_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="auto",
)

# ==========================================
# Source and destination
# ==========================================

SOURCE_KEY = (
    "DUAE/year=2026/month=09/day=06/"
    "property/profiles-data/profiles-data.xlsx"
)

DESTINATION_KEY = (
    "DUAE/year=2026/month=09/day=06/"
    "property/property-for-rent/profiles-data/profiles-data.xlsx"
)

print(f"Source:      {SOURCE_KEY}")
print(f"Destination: {DESTINATION_KEY}")

# ==========================================
# 1. Copy file to new location
# ==========================================

print("\nCopying file...")

client.copy_object(
    Bucket=BUCKET_NAME,
    CopySource={
        "Bucket": BUCKET_NAME,
        "Key": SOURCE_KEY
    },
    Key=DESTINATION_KEY
)

print("✅ File copied successfully.")

# ==========================================
# 2. Verify destination exists
# ==========================================

print("\nVerifying destination...")

client.head_object(
    Bucket=BUCKET_NAME,
    Key=DESTINATION_KEY
)

print("✅ Destination file verified.")

# ==========================================
# 3. Delete old file
# ==========================================

print("\nDeleting old file...")

client.delete_object(
    Bucket=BUCKET_NAME,
    Key=SOURCE_KEY
)

print("✅ Old file deleted.")

# ==========================================
# 4. Verify old file is gone
# ==========================================

print("\nVerifying old file removal...")

try:
    client.head_object(
        Bucket=BUCKET_NAME,
        Key=SOURCE_KEY
    )

    print("❌ Old file still exists!")

except client.exceptions.ClientError as e:
    if e.response["Error"]["Code"] in ["404", "NoSuchKey"]:
        print("✅ Old file no longer exists.")
    else:
        raise

print("\n========== RESULT ==========")
print("✅ File moved successfully!")
print(f"From: {SOURCE_KEY}")
print(f"To:   {DESTINATION_KEY}")