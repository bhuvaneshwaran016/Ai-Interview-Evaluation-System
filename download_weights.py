import os
import urllib.request

user_dir = os.path.expanduser('~')
weight_dir = os.path.join(user_dir, '.deepface', 'weights')
os.makedirs(weight_dir, exist_ok=True)

file_path = os.path.join(weight_dir, 'facial_expression_model_weights.h5')
url = 'https://github.com/serengil/deepface_models/releases/download/v1.0/facial_expression_model_weights.h5'

print(f"Downloading weights to {file_path}...")
urllib.request.urlretrieve(url, file_path)
print("Download complete!")
