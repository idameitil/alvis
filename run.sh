#!/bin/bash

echo "========================================"
echo "  alvis — development server"
echo "========================================"
echo ""
echo "Building and starting Docker container..."
echo "Open your browser at: http://localhost:5001"
echo "Press Ctrl+C to stop"
echo ""

docker-compose up --build
