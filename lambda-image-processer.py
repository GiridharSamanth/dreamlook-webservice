import json
import base64
import boto3
from botocore.exceptions import BotoCoreError, ClientError
import uuid
from PIL import Image
import io
import os
import http.client
from requests_toolbelt.multipart import decoder
import mimetypes

s3_client = boto3.client('s3')
s3_bucket = "dreamlook-temp"
public_url = "https://dreamlook-temp.s3.ap-south-1.amazonaws.com"
photoroom_apikkey = "sandbox_d1e7de9baa38ad47aa0cd15c31a2856b1c4dd297"
FORMAT_TO_CONTENT_TYPE = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "ICO": "image/vnd.microsoft.icon",
    "WEBP": "image/webp"
}
CONTENT_TYPE_TO_FORMAT = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/gif": "GIF",
        "image/bmp": "BMP",
        "image/tiff": "TIFF",
        "image/webp": "WEBP"
    }
def test_function():
    x = {
        "foo": "bar3"
    }
    return {
        'statusCode': 200,
        'body': json.dumps(x)
    }

# S3 related functions
def open_image_from_s3(key):
    """
    Fetch an image from S3 and open it as a PIL Image object.
    """
    try:
        # Get the object from S3
        response = s3_client.get_object(Bucket=s3_bucket, Key=key)
        # Open the image using PIL
        image = Image.open(io.BytesIO(response['Body'].read()))
        return image
    except Exception as e:
        print(f"Failed to open image from S3: {e}")
        return None

def save_to_s3(file_path, content, content_type):
    try:
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=file_path,
            Body=content,
            ContentType=content_type
        )
        return True
    except Exception as e:
        print(f"Failed to save to S3: {e}")
        return False

# Image processing related functions
def stich_partner_photos(partnerOne_photo_path, partnerTwo_photo_path, output_path, spacing=0):
    """
    Combine the bride and groom images into one canvas with proper alignment and dynamic sizing.
    """
    max_groom_height=800
    min_groom_height = 740
    min_bride_height=740
    max_bride_height=800


    # Load images with transparency
    #bride = Image.open(bride_path).convert("RGBA")
    #groom = Image.open(groom_path).convert("RGBA")
    bride = open_image_from_s3(partnerTwo_photo_path)
    groom = open_image_from_s3(partnerOne_photo_path)


    # Scale groom based on the ratio
    bride_width, bride_height = bride.size
    groom_width, groom_height = groom.size

    bride_to_groom_ratio = 0.85  # Minimum ratio

    # Scale the groom to the maximum height
    groom_width, groom_height = groom.size
    if (groom_height < min_groom_height):
        groom_height = min_groom_height
    groom_scale = max_groom_height / groom_height
    groom_resized = groom.resize(
        (int(groom_width * groom_scale), int(max_groom_height)), Image.Resampling.LANCZOS
    )

    # Scale the bride proportionally based on the adjusted ratio
    bride_width, bride_height = bride.size
    desired_bride_height = max_groom_height * bride_to_groom_ratio
    if (desired_bride_height < min_bride_height):
        desired_bride_height = min_bride_height
    elif (desired_bride_height > max_bride_height):
        desired_bride_height = max_bride_height
    bride_scale = desired_bride_height / bride_height
    bride_resized = bride.resize(
        (int(bride_width * bride_scale), int(desired_bride_height)), Image.Resampling.LANCZOS
    )

    # Calculate canvas size with transparent background
    canvas_width = bride_resized.width + groom_resized.width + spacing
    canvas_height = max(bride_resized.height, groom_resized.height)
    canvas = Image.new("RGB", (canvas_width, canvas_height), (255,255,255))

    # Paste groom and bride images onto the transparent canvas
    groom_x = 0
    groom_y = canvas_height - groom_resized.height
    bride_x = groom_resized.width + spacing
    bride_y = canvas_height - bride_resized.height

    canvas.paste(groom_resized, (groom_x, groom_y), groom_resized)
    canvas.paste(bride_resized, (bride_x, bride_y), bride_resized)

    # Save the modified image to an in-memory buffer
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    buffer.seek(0)  # Reset buffer position

    # Save to S3
    success = save_to_s3(output_path, buffer.getvalue(), "image/png")
    buffer.close()

    if success:
        print(f"Image successfully saved to S3 at {output_path}")
        return True
    else:
        print("Failed to save the processed image to S3.")
        return False
    
def get_image_metadata(image, file_path=None):
    """
    Retrieve the filename, content, and content type of a PIL Image.
    """
    # Determine filename
    filename = os.path.basename(file_path) if file_path else "unknown"
    
    # Get content type
    # content_type = FORMAT_TO_CONTENT_TYPE.get(image.format, "application/octet-stream")
    content_type, _ = mimetypes.guess_type(file_path)
    format = CONTENT_TYPE_TO_FORMAT.get(content_type)
    # Get raw content
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    content = buffer.getvalue()
    buffer.close()

    return {
        "filename": filename,
        "content": content,
        "content_type": content_type or "application/octet-stream"
    }

def remove_background(input_image_path, output_image_path):
    try:
        # Define multipart boundary
        boundary = '----------{}'.format(uuid.uuid4().hex)
        input_image = open_image_from_s3(input_image_path)
        metadata = get_image_metadata(input_image, input_image_path)
        filename = metadata['filename']
        content_type = metadata['content_type']
        image_data = metadata['content']

        print('metadata:', metadata)

        body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image_file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
        ).encode('utf-8') + image_data + f"\r\n--{boundary}--\r\n".encode('utf-8')
        print('The body', body)

        conn = http.client.HTTPSConnection('sdk.photoroom.com')
        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'x-api-key': photoroom_apikkey
        }

        # Make the POST request
        conn.request('POST', '/v1/segment', body=body, headers=headers)
        response = conn.getresponse()

        is_successful = False
        # Handle the response
        if response.status == 200:
            print('API was successful')
            response_data = response.read()
            # with open(output_image_path, 'wb') as out_f:
            #     out_f.write(response_data)
            # print("Image saved to", output_image_path)
            content_type = "image/png"  # Replace with the correct content type if known
            # Save to S3
            print("Saving final copy to s3")
            success = save_to_s3(output_image_path, response_data, content_type)
            if success:
                print(f"Image successfully saved to S3 at {output_image_path}")
            else:
                print("Failed to save the image to S3.")
            is_successful = success
        else:
            print(f"Error: {response.status} - {response.reason}")
            print(response.read())
            
        # Close the connection
        conn.close()
        return is_successful
    except Exception as e:
        print(f"Failed to remove background: {e}")
        return False

def process_request(event):
    try:
        # Parse the input payload
        body = json.loads(event['body'])
        
        if not isinstance(body, list):
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid payload format. Expected a list of files."})
            }

        # Process each file in the payload
        raw_files_store = {}
        for file in body:
            bucket = file.get('bucket')
            key = file.get('key')
            name = file.get('name')
            raw_files_store[name] = key

        # Step 2: If partner images exists then stitch them and save back to s3.
        if ('partnerOne' in raw_files_store and 'partnerTwo' in raw_files_store):
            unique_name = uuid.uuid4().hex
            step_two_photo_path = f"image-processing/partners-stitched/{unique_name}.jpg"
            is_saved = stich_partner_photos(raw_files_store['partnerOne'], raw_files_store['partnerTwo'], step_two_photo_path)
            if is_saved:
                step_two_photo = step_two_photo_path
            else:
                return {
                    "statusCode": 500,
                    "body": {
                        "message": "Failed to process your request at step 2"
                }
            }    
        elif ('couple' in raw_files_store):
            step_two_photo = raw_files_store['couple']
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Required images not sent."})
            }

        # Step 3:
        if step_two_photo == None:
            return {
                "statusCode": 500,
                "body": {
                    "message": "Failed to start step 3 as the image was not found"
                }
            }
        final_path= ""
        unique_name = uuid.uuid4().hex
        step_three_photo_path = f"image-processing/background-removed/{unique_name}.png"
        is_background_removed = remove_background(step_two_photo, step_three_photo_path)
        if is_background_removed:
            final_path = step_three_photo_path

        # Construct the response
        response = {
            "statusCode": 200,
            "body": {
                # "data": data,
                "image_info": f"{public_url}/{final_path}",
                "version": "3"
            }
        }
        
        return response
        
    except Exception as e:
        print(f"Error processing images: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal Server Error", "details": str(e)})
        }

def lambda_handler(event, context):
    try:
        # test function to debug
        #result = test_function()
        #return result

        # Call the business logic function
        response = process_request(event)
        return response
    except ValueError as ve:
        return {
            "statusCode": 400,
            "body": str(ve)
        }
    except RuntimeError as re:
        return {
            "statusCode": 500,
            "body": str(re)
        }
    except Exception as e:
        # Catch-all for unexpected errors
        return {
            "statusCode": 500,
            "body": f"Unexpected error: {str(e)}"
        }
