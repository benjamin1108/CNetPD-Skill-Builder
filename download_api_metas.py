#!/usr/bin/env python3
"""
Script to download all API metadata from Aliyun API and organize them
into directories based on category names.
"""

import os
import json
import requests
from pathlib import Path
from urllib.parse import urljoin


# Base URLs for the API
BASE_URL = "https://api.aliyun.com/meta/v1/"
PRODUCTS_URL = urljoin(BASE_URL, "products.json")


def create_directory(path):
    """Create directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)
    print(f"Ensured directory exists: {path}")


def download_file(url, filename):
    """Download a file from URL and save it locally."""
    try:
        print(f"Downloading: {url}")
        response = requests.get(url)
        response.raise_for_status()
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(response.json(), f, ensure_ascii=False, indent=2)
        
        print(f"Downloaded: {filename}")
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False


def main():
    # Create main directory for storing metadata
    main_dir = "api_metadata"
    create_directory(main_dir)
    
    # Download the list of all products
    print("Downloading products list...")
    try:
        response = requests.get(PRODUCTS_URL)
        response.raise_for_status()
        products_data = response.json()
        print(f"Found {len(products_data)} products")
    except Exception as e:
        print(f"Failed to download products list: {e}")
        return
    
    # Process each product
    count = 0
    for product in products_data:
        code = product.get("code")
        versions = product.get("versions", [])
        version = product.get("defaultVersion") or (versions[0] if versions else None)
        category_name = product.get("categoryName", "Uncategorized")
        category2_name = product.get("category2Name", "Uncategorized")
        
        if not code or not version:
            print(f"Skipping product with missing code or version: {product.get('name', 'Unknown')}")
            continue
        
        # Create directory structure: category2/category/
        # Sanitize directory names to remove invalid characters
        category_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in category_name)
        category2_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in category2_name)
        
        category_dir = os.path.join(main_dir, category2_name, category_name)
        create_directory(category_dir)
        
        # Download API docs for this product
        api_docs_url = f"{BASE_URL}products/{code}/versions/{version}/api-docs.json"
        filename = os.path.join(category_dir, f"{code}.json")
        
        # Download and save the file
        if download_file(api_docs_url, filename):
            count += 1
    
    print(f"Download complete! Downloaded {count} API documents.")


if __name__ == "__main__":
    main()