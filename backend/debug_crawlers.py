#!/usr/bin/env python3
"""
Debug script to test crawlers and see what's happening.
"""
import asyncio
import httpx


async def debug_sephora(upc: str) -> None:
    """Debug Sephora crawler to see what we're getting."""
    
    print(f"🔍 Testing Sephora search for UPC: {upc}")
    print("=" * 60)
    
    url = f"https://www.sephora.com/search?keyword={upc}"
    print(f"URL: {url}\n")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            
            print(f"Status Code: {response.status_code}")
            print(f"Final URL: {response.url}")
            print(f"Response Headers:")
            for key, value in response.headers.items():
                if key.lower() in ['content-type', 'server', 'cf-ray', 'x-frame-options']:
                    print(f"  {key}: {value}")
            
            # Check for CloudFlare block
            if 'cf-ray' in response.headers:
                print("\n⚠️  CloudFlare detected!")
            
            # Check response content
            content = response.text
            print(f"\nResponse Length: {len(content)} bytes")
            
            # Check for common block indicators
            if "captcha" in content.lower():
                print("❌ CAPTCHA detected in response!")
            if "access denied" in content.lower():
                print("❌ Access Denied detected!")
            if "robot" in content.lower():
                print("❌ Robot detection triggered!")
            if "challenge" in content.lower():
                print("⚠️  Challenge page detected (likely JavaScript required)")
            
            # Save response for inspection
            with open("debug_sephora_response.html", "w") as f:
                f.write(content)
            print("\n📄 Full response saved to: debug_sephora_response.html")
            
            # Check if we got actual product results
            if "/product/" in content:
                print("✅ Found product links in response!")
                # Count how many
                count = content.count("/product/")
                print(f"   Found approximately {count} product references")
            else:
                print("❌ No product links found in response")
            
        except Exception as e:
            print(f"❌ Error: {e}")


async def debug_google_shopping(upc: str) -> None:
    """Debug Google Shopping search."""
    
    print(f"\n🔍 Testing Google Shopping for UPC: {upc}")
    print("=" * 60)
    
    url = f"https://www.google.com/search?tbm=shop&q={upc}"
    print(f"URL: {url}\n")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            
            print(f"Status Code: {response.status_code}")
            print(f"Final URL: {response.url}")
            
            content = response.text
            print(f"Response Length: {len(content)} bytes")
            
            # Save response
            with open("debug_google_response.html", "w") as f:
                f.write(content)
            print("📄 Full response saved to: debug_google_response.html")
            
            # Check for products
            if "shopping" in content.lower() or "$" in content:
                print("✅ Looks like shopping results!")
            
            # Look for price patterns
            import re
            prices = re.findall(r'\$\d+\.?\d*', content)
            if prices:
                print(f"✅ Found prices: {prices[:5]}...")
            else:
                print("❌ No prices found")
                
        except Exception as e:
            print(f"❌ Error: {e}")


async def debug_direct_product_search(brand: str, product: str) -> None:
    """Try searching with brand + product name instead of UPC."""
    
    query = f"{brand} {product}"
    print(f"\n🔍 Testing Google Shopping with brand+product: {query}")
    print("=" * 60)
    
    import urllib.parse
    url = f"https://www.google.com/search?tbm=shop&q={urllib.parse.quote(query)}"
    print(f"URL: {url}\n")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            
            print(f"Status Code: {response.status_code}")
            
            content = response.text
            print(f"Response Length: {len(content)} bytes")
            
            # Save response
            with open("debug_brand_search_response.html", "w") as f:
                f.write(content)
            print("📄 Full response saved to: debug_brand_search_response.html")
            
            # Look for price patterns
            import re
            prices = re.findall(r'\$\d+\.?\d*', content)
            if prices:
                print(f"✅ Found prices: {prices[:5]}...")
            else:
                print("❌ No prices found")
                
        except Exception as e:
            print(f"❌ Error: {e}")


async def main():
    # Test UPCs from the assignment
    test_cases = [
        ("885190822010", "Pixi", "Glow Mud Mask"),  # Medium
        ("850029397809", "DIBS Beauty", "No Pressure Lip Liner"),  # Easy
    ]
    
    for upc, brand, product in test_cases:
        print("\n" + "=" * 70)
        print(f"TESTING: {brand} - {product}")
        print("=" * 70)
        
        await debug_sephora(upc)
        await debug_google_shopping(upc)
        await debug_direct_product_search(brand, product)
        
        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
