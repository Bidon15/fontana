#!/usr/bin/env python
"""
Debug script to test raw socket connections to Celestia node.
This bypasses the PyLestia client to see if we can connect directly.
"""
import os
import sys
import socket
import requests
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("celestia-debug")

def test_socket_connection(host='localhost', port=26658):
    """Test direct socket connection to the specified host and port."""
    try:
        logger.info(f"Testing TCP socket connection to {host}:{port}...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)  # 3 second timeout
            result = s.connect_ex((host, port))
            if result == 0:
                logger.info(f"Socket connection to {host}:{port} SUCCESSFUL")
                return True
            else:
                logger.error(f"Socket connection to {host}:{port} FAILED with error code {result}")
                return False
    except Exception as e:
        logger.error(f"Socket connection error: {str(e)}")
        return False

def test_http_request(url="http://localhost:26658"):
    """Test HTTP request to the specified URL using requests library."""
    try:
        logger.info(f"Testing HTTP request to {url}...")
        response = requests.get(url, timeout=3)
        logger.info(f"HTTP response status: {response.status_code}")
        logger.info(f"HTTP response: {response.text[:200]}...")  # First 200 chars
        return True
    except Exception as e:
        logger.error(f"HTTP request error: {str(e)}")
        return False

def test_jsonrpc_request(url="http://localhost:26658", auth_token=None):
    """Test JSON-RPC request to the specified URL."""
    try:
        logger.info(f"Testing JSON-RPC request to {url}...")
        headers = {
            "Content-Type": "application/json",
        }
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "node.Info",
            "params": []
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=3)
        logger.info(f"JSON-RPC response status: {response.status_code}")
        logger.info(f"JSON-RPC response: {json.dumps(response.json(), indent=2)}")
        return True
    except Exception as e:
        logger.error(f"JSON-RPC request error: {str(e)}")
        return False

def main():
    """Run all tests with different variants."""
    # Get auth token from environment
    auth_token = os.environ.get("CELESTIA_AUTH_TOKEN")
    
    # Test with localhost
    test_socket_connection('localhost', 26658)
    test_socket_connection('127.0.0.1', 26658)
    
    # Test HTTP requests
    test_http_request("http://localhost:26658")
    test_http_request("http://127.0.0.1:26658")
    
    # Test JSON-RPC requests
    test_jsonrpc_request("http://localhost:26658", auth_token)
    test_jsonrpc_request("http://127.0.0.1:26658", auth_token)

if __name__ == "__main__":
    main()
