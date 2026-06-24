#!/bin/bash

API_IMAGE=transaction-api

docker build --platform=linux/x86_64 -f ./Dockerfile -t $API_IMAGE:latest .

# Uncomment below to push image to ECR in AWS
# You'll need a profile (esgf2) managed by vault for account 730335463484

# aws ecr get-login-password \
#     --profile esgf2 \
#     --region us-east-1 | docker login --username AWS --password-stdin 730335463484.dkr.ecr.us-east-1.amazonaws.com

# docker tag $API_IMAGE:latest 730335463484.dkr.ecr.us-east-1.amazonaws.com/$API_IMAGE:latest
# docker push 730335463484.dkr.ecr.us-east-1.amazonaws.com/$API_IMAGE:latest