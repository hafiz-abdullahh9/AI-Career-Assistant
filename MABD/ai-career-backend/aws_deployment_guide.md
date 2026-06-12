# AWS Deployment Guide: AI Career Assistant Backend

This guide outlines how to deploy the FastAPI backend application to AWS using **Amazon RDS (PostgreSQL)** and **AWS App Runner** (or **AWS ECS Fargate**).

---

## Architecture Overview

```mermaid
graph TD
    User([Job Seeker / Client]) --> |HTTPS| AppRunner[AWS App Runner / ECS Fargate]
    AppRunner --> |Private Subnet| RDS[(AWS RDS PostgreSQL)]
    AppRunner --> |Outbound HTTP| LLM[Google Gemini / OpenAI APIs]
```

---

## Step 1: Set Up Amazon RDS (PostgreSQL)

AWS App Runner is stateless. We must use a managed persistent database.

1. Go to the **Amazon RDS Console**.
2. Click **Create database**.
3. Configure the database:
   * **Engine options:** PostgreSQL
   * **Templates:** Free Tier (for dev/test) or Dev/Test
   * **DB instance identifier:** `career-assistant-db`
   * **Master username:** `postgres`
   * **Master password:** *Choose a secure password*
   * **Instance configuration:** `db.t4g.micro` (Free tier eligible)
   * **Connectivity:** 
     * **Public access:** No (for security, keep it inside your VPC)
     * Create/Select a VPC security group that allows inbound traffic on port `5432` from your App Runner service/VPC.
4. Click **Create database**.
5. Once active, note down the **Endpoint** and **Port** under the "Connectivity & security" tab.
   * Your connection string will look like: `postgresql://postgres:YOUR_PASSWORD@YOUR_ENDPOINT:5432/postgres`

---

## Step 2: Container Registry Setup (Amazon ECR)

We need to push the built Docker image to AWS Elastic Container Registry (ECR).

1. Go to the **Amazon ECR Console**.
2. Click **Create repository**.
   * **Visibility settings:** Private
   * **Repository name:** `ai-career-backend`
3. Click **Create repository**.
4. Select the repository and click **View push commands**. 
5. Run these commands locally in your terminal to build and push your image (make sure AWS CLI is installed and configured):

```bash
# 1. Authenticate Docker with AWS
aws ecr get-login-password --region <your-region> | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.<your-region>.amazonaws.com

# 2. Build the Docker Image
docker build -t ai-career-backend .

# 3. Tag the Image
docker tag ai-career-backend:latest <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/ai-career-backend:latest

# 4. Push the Image to AWS ECR
docker push <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/ai-career-backend:latest
```

---

## Step 3: Deploy using AWS App Runner (Recommended)

AWS App Runner is the easiest, most cost-effective way to run a containerized API with automatic SSL.

1. Go to the **AWS App Runner Console** and click **Create service**.
2. **Source and deployment:**
   * **Repository type:** Container registry
   * **Provider:** Amazon ECR
   * **Container image URI:** Browse and select `<your-account-id>.dkr.ecr.<your-region>.amazonaws.com/ai-career-backend:latest`
   * **Deployment settings:** Automatic (deploys automatically whenever a new image is pushed to ECR)
3. **Configure service:**
   * **Service name:** `ai-career-backend-service`
   * **Virtual CPU & Memory:** 1 vCPU, 2 GB (adequate for API workloads)
   * **Environment variables:** Add the following key-value pairs:
     * `DATABASE_URL` = `postgresql://postgres:YOUR_PASSWORD@YOUR_RDS_ENDPOINT:5432/postgres`
     * `LLM_PROVIDER` = `gemini` (or `openai`)
     * `GEMINI_API_KEY` = `YOUR_GEMINI_KEY`
     * `OPENAI_API_KEY` = `YOUR_OPENAI_KEY`
   * **Port:** `8000`
4. **Networking:**
   * Ensure that App Runner has outbound VPC connectivity configured so it can securely access the RDS database instance.
5. Click **Create & Deploy**.
6. Once deployment finishes, AWS will provide a secure HTTPS endpoint (e.g., `https://xxxxxx.us-east-1.awsapprunner.com`). Access the Swagger docs at `https://xxxxxx.us-east-1.awsapprunner.com/docs`.

---

## Troubleshooting & Best Practices

1. **Database Connection Issues:** Make sure the security group assigned to your RDS database allows inbound traffic on port `5432` from the Security Group associated with your App Runner VPC connector.
2. **Startup Timeouts:** Ensure that `main:app` binds correctly to host `0.0.0.0` (which is already configured in the `Dockerfile`).
3. **Logs Monitoring:** Check logs under the **Log Streams** tab in App Runner to see Python tracebacks if the app fails to start.
