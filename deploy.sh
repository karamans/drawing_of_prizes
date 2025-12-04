#!/bin/bash

# Function to check .env
check_env() {
    if [ ! -f .env ]; then
        echo "Error: .env file not found!"
        echo "Please create .env file from env.example"
        exit 1
    fi
}

# Function to check Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "Docker not found. Please install Docker first."
        exit 1
    fi
}

check_env
check_docker

CMD=$1

if [ "$CMD" == "auth" ]; then
    echo "Starting authentication manager..."
    # Run a temporary container interactively just for auth
    # We mount data/ so sessions persist
    # We mount .env so auth.py can read config
    docker-compose run --rm --entrypoint "python auth.py" bot
    
elif [ "$CMD" == "logs" ]; then
    docker-compose logs -f

elif [ "$CMD" == "stop" ]; then
    docker-compose down

else
    echo "Deploying bot in background..."
    docker-compose up -d --build
    echo "Deployment successful!"
    echo "Use './deploy.sh logs' to see logs."
    echo "Use './deploy.sh auth' to manage accounts."
    echo "Use './deploy.sh stop' to stop."
fi
