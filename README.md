to deploy to gcp use the following commands 


sudo gcloud functions deploy transcribe \
  --runtime python312 \
  --trigger-http \
  --set-secrets OPEN_API_KEY=projects/{projectId}/secrets/OPENAI_API_KEY/versions/latest
  --allow-unauthenticated \
  --entry-point transcribe
