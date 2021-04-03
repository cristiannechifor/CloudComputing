import logging
import os
import json
import six
import base64
from google.cloud import texttospeech
from google.cloud import translate_v2 as translate
from flask import Flask, request
from google.cloud import storage

app = Flask(__name__)

# Configure this environment variable via app.yaml
CLOUD_STORAGE_BUCKET = os.environ['CLOUD_STORAGE_BUCKET']


@app.route('/')
def index():
    return """
<form method="POST" action="/books" enctype="multipart/form-data">
    <input type="file" name="file">
    <input type="submit">
</form>
<form method="GET" action="/books">
    <input type="submit" value="List books">
</form>
"""


@app.route('/books', methods=['POST'])
def book_upload():
    """Process the uploaded file and upload it to Google Cloud Storage."""
    uploaded_file = request.files.get('file')

    if not uploaded_file:
        return 'No file uploaded.', 400

    # Create a Cloud Storage client.
    gcs = storage.Client()

    # Get the bucket that the file will be uploaded to.
    bucket = gcs.get_bucket(CLOUD_STORAGE_BUCKET)

    # Create a new blob and upload the file's content.
    blob = bucket.blob(uploaded_file.filename)

    blob.upload_from_string(
        uploaded_file.read(),
        content_type=uploaded_file.content_type
    )

    # The public URL can be used to directly access the uploaded file via HTTP.
    return blob.public_url

@app.route('/books', methods=['GET'])
def book_list():
    storage_client = storage.Client()

    # Note: Client.list_blobs requires at least package version 1.17.0.
    blobs = storage_client.list_blobs(CLOUD_STORAGE_BUCKET)
    
    books = ""
    for blob in blobs:
        line = blob.name + "<form method=\"POST\" action=\"/books/translate?book="+ blob.name +"\"><input type=\"submit\" value=\"Translate book\"></form>"
        line += "<form method=\"POST\" action=\"/books/tts?book="+ blob.name +"\"><input type=\"submit\" value=\"Read book\"></form>"
        books += line # blob.name + " <br> "
    
    return books

@app.route('/books/translate', methods=['POST'])
def book_translate():
    bname = request.args.get('book')

    btext = book_get_text(bname)
    translate_client = translate.Client()
    result = translate_client.translate(btext, target_language="ro")

    return result["translatedText"]

def book_get_text(bname):
    storage_client = storage.Client()

    # Note: Client.list_blobs requires at least package version 1.17.0.
    blobs = storage_client.get_bucket(CLOUD_STORAGE_BUCKET)

    blob = blobs.get_blob(bname)
    btext = blob.download_as_string()
    if isinstance(btext, six.binary_type):
        btext = btext.decode("utf-8")

    return btext

@app.route('/books/tts', methods=['POST'])
def book_tts():
    bname = request.args.get('book')

    btext = book_get_text(bname)
    
    client = texttospeech.TextToSpeechClient()
    
    synthesis_input = texttospeech.SynthesisInput(text=btext)
    voice = texttospeech.VoiceSelectionParams(language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

    base64_encoded_data = base64.b64encode(response.audio_content)
    base64_message = base64_encoded_data.decode('utf-8')

    return "<audio controls=\"controls\" autobuffer=\"autobuffer\" autoplay=\"autoplay\"><source src=\"data:audio/mp3;base64,"+ base64_message +"\"></audio>"

@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500


if __name__ == '__main__':
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host='127.0.0.1', port=8080, debug=True)