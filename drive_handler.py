import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import config

SCOPE = ['https://www.googleapis.com/auth/drive']


class DriveHandler:
    def __init__(self):
        creds = service_account.Credentials.from_service_account_file(
            config.CREDENTIALS_FILE, scopes=SCOPE)
        self.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        print("✅ Conectado a Google Drive")

    def subir_archivo(self, ruta_local, nombre_archivo):
        """
        Sube un archivo local a la carpeta configurada en Drive.
        Devuelve el webViewLink del archivo subido.
        """
        metadata = {
            'name': nombre_archivo,
            'parents': [config.DRIVE_FOLDER_ID]
        }
        media = MediaFileUpload(ruta_local, mimetype='application/pdf', resumable=True)

        archivo = self.service.files().create(
            body=metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True,
        ).execute(num_retries=3)

        return archivo.get('webViewLink')