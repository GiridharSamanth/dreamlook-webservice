
import AWS from 'aws-sdk';
const s3 = new AWS.S3();

const test = async() => {
  const response = {
    statusCode: 200,
    body: JSON.stringify('Hello from Lambda!!'),
  };
  return response;
}

const getSignedUrl = async(event) => {
  try {
    const requestBody = JSON.parse(event.body);
    if (!Array.isArray(requestBody)) {
        return {
            statusCode: 400,
            body: JSON.stringify({ error: 'Request body must be an array' }),
        };
    }

    // Define S3 parameters
    const bucketName = 'dreamlook-temp'; // Replace with your S3 bucket name
    const expirationTime = 60 * 5; // URL expiration time in seconds (5 minutes)
    const raw_image_path = 'image-processing/raw-uploads'

    const signedUrls = requestBody.map((file) => {
      const { fileName, mimeType, name } = file;

      if (!fileName || !mimeType || !name) {
          throw new Error('Invalid file data in request body');
      }

      const params = {
          Bucket: bucketName,
          Key: `${raw_image_path}/${fileName}`,
          Expires: expirationTime,
          ContentType: mimeType,
      };

      const signedUrl = s3.getSignedUrl('putObject', params);

      return {
          name,
          signedUrl,
      };
    });

    // Return the signed URLs
    return {
        statusCode: 200,
        body: JSON.stringify(signedUrls),
    };

  } catch (error) {
      console.error('Error generating pre-signed URL:', error);
      return {
          statusCode: 500,
          body: JSON.stringify({ error: 'Internal Server Error' }),
      };
  }
}

export const handler = async (event) => {
  // TODO implement
  const response = await getSignedUrl(event);
  return response
};
