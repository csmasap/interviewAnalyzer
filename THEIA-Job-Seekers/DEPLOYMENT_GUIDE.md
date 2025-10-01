# THEIA Deployment Guide

This guide will help you deploy the THEIA Interview Prep application to Google Cloud Platform.

## Prerequisites

1. **Google Cloud CLI**: Install and authenticate
   ```bash
   # Install gcloud CLI (if not already installed)
   curl https://sdk.cloud.google.com | bash
   exec -l $SHELL
   
   # Authenticate
   gcloud auth login
   gcloud auth application-default login
   ```

2. **Project Setup**: Ensure you have a Google Cloud project
   ```bash
   # Set your project ID
   gcloud config set project theia-job-seekers
   ```

3. **Domain Configuration**: Set up your custom domain (`theiajobs.ai`)
   - Verify domain ownership in Google Cloud Console
   - Create DNS records (see Domain Setup section below)

## Quick Deployment

Run the automated deployment script:

```bash
./deploy.sh
```

This will:
- Deploy the backend to Cloud Run
- Build and deploy the frontend to Cloud Storage
- Configure the bucket for website hosting
- Set up proper caching and permissions

## Manual Deployment Steps

### 1. Backend Deployment

Deploy the backend API to Cloud Run:

```bash
gcloud builds submit --config cloudbuild-backend.yaml \
  --substitutions _SERVICE_NAME=theia-backend,_REGION=us-central1
```

### 2. Frontend Deployment

Deploy the frontend to Cloud Storage:

```bash
# Get the backend URL first
BACKEND_URL=$(gcloud run services describe theia-backend --region=us-central1 --format="value(status.url)")

# Deploy frontend
gcloud builds submit --config cloudbuild-frontend.yaml \
  --substitutions _BUCKET=theiajobs.ai,_BACKEND_URL=$BACKEND_URL
```

## Domain Setup

### DNS Configuration

To make `www.theiajobs.ai` work with Google Cloud Storage:

1. **Create CNAME records** in your DNS provider:
   ```
   www.theiajobs.ai → c.storage.googleapis.com
   theiajobs.ai → c.storage.googleapis.com
   ```

2. **Verify domain ownership** in Google Cloud Console:
   - Go to Cloud Storage → Settings → Domain verification
   - Add `theiajobs.ai` and follow verification steps

### Bucket Configuration

The deployment script automatically:
- Creates the bucket named `theiajobs.ai`
- Sets it up for website hosting
- Configures proper permissions and caching

## Troubleshooting

### "NoSuchKey" Error

This error means the bucket doesn't have the correct files. Common causes:

1. **Wrong bucket name**: Ensure the bucket name matches your domain exactly
2. **Missing index.html**: The React build must be deployed, not raw source files
3. **Incorrect deployment**: Use the updated `cloudbuild-frontend.yaml`

### Build Failures

1. **Node.js issues**: Ensure Node.js 18+ is available in Cloud Build
2. **Missing dependencies**: Check that `package.json` is correct
3. **Build errors**: Check Cloud Build logs in Google Cloud Console

### Backend Connection Issues

1. **CORS errors**: Backend should allow your frontend domain
2. **Authentication**: Ensure Cloud Run service allows unauthenticated requests
3. **API URL**: Verify `api-base.txt` contains the correct backend URL

## Configuration Files

### cloudbuild-frontend.yaml
- Builds the React app with production optimizations
- Copies legacy HTML files for compatibility
- Sets up proper caching headers
- Configures bucket for website hosting

### cloudbuild-backend.yaml
- Deploys FastAPI backend to Cloud Run
- Configures memory, CPU, and scaling settings
- Sets environment variables

### Dockerfile
- Multi-stage build for Python backend
- Installs system dependencies
- Optimized for Cloud Run deployment

## Environment Variables

### Backend (.env or Cloud Run environment)
```
# Required for production
GOOGLE_CLOUD_PROJECT=theia-job-seekers
OPENAI_API_KEY=your_openai_key
SALESFORCE_CONSUMER_KEY=your_sf_key
SALESFORCE_CONSUMER_SECRET=your_sf_secret
SALESFORCE_USERNAME=your_sf_username
SALESFORCE_PASSWORD=your_sf_password
REDIS_URL=your_redis_url
```

### Frontend (build-time)
```
REACT_APP_API_URL=https://theia-job-seekers-603965392227.us-central1.run.app
```

## Security Considerations (SOC2 Compliance)

1. **HTTPS Only**: All traffic uses HTTPS
2. **Secure Headers**: Proper caching and security headers set
3. **Authentication**: JWT tokens for API access
4. **Data Protection**: Sensitive data encrypted in transit and at rest
5. **Access Control**: Proper IAM roles and permissions
6. **Audit Logging**: Cloud Build and Cloud Run provide audit trails

## Monitoring and Logging

- **Cloud Build**: Check build logs in Google Cloud Console
- **Cloud Run**: Monitor backend performance and errors
- **Cloud Storage**: Monitor bucket access and performance
- **Error Reporting**: Automatic error tracking for backend issues

## Cost Optimization

- **Cloud Run**: Pay-per-request pricing
- **Cloud Storage**: Standard storage class for frontend files
- **Cloud Build**: Free tier includes 120 build-minutes per day
- **Caching**: Proper cache headers reduce bandwidth costs

## Support

If you encounter issues:

1. Check Cloud Build logs in Google Cloud Console
2. Verify DNS propagation using `dig` or online tools
3. Test backend health endpoint: `curl https://your-backend-url/health`
4. Check browser developer tools for frontend errors

## Next Steps

After deployment:

1. **Test the application** end-to-end
2. **Set up monitoring** and alerting
3. **Configure backup** strategies
4. **Implement CI/CD** pipelines for automated deployments
5. **Security audit** and penetration testing
