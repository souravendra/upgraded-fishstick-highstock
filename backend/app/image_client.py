"""
Client for the Node.js Image Verification Service.

Uses Transformers.js (CLIP model) for:
- Image-text similarity verification
- Product type detection
- Visual color/shade verification
"""

import os
import httpx
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ImageVerificationResult:
    """Result from image verification."""

    is_verified: bool
    confidence: int  # 0-100
    brand_detected: bool
    product_detected: bool
    reasoning: str
    raw_scores: Optional[Dict[str, float]] = None


class ImageVerificationClient:
    """
    Client for the Node.js Image Verification Service.

    The service must be running on localhost:3001 (or configured URL).
    Start it with: cd image-service && npm start

    Configure via environment variable: IMAGE_SERVICE_URL
    """

    def __init__(self, base_url: Optional[str] = None):
        # Allow configuration via environment variable
        self.base_url = base_url or os.getenv(
            "IMAGE_SERVICE_URL", "http://localhost:3001"
        )
        self.client = httpx.AsyncClient(timeout=60.0)  # Long timeout for model loading
        self._is_available: Optional[bool] = None

    async def is_available(self) -> bool:
        """Check if the image service is running."""
        if self._is_available is not None:
            return self._is_available

        try:
            response = await self.client.get(f"{self.base_url}/health")
            self._is_available = response.status_code == 200
        except Exception:
            self._is_available = False

        return self._is_available

    async def verify_image(
        self,
        image_url: str,
        expected_brand: str,
        expected_product: str,
        expected_color: Optional[str] = None,
        expected_size: Optional[str] = None,
    ) -> ImageVerificationResult:
        """
        Verify that an image matches the expected product.

        Uses CLIP model to compare image to text descriptions.

        Args:
            image_url: URL of the product image
            expected_brand: Expected brand name (e.g., "DIBS Beauty")
            expected_product: Expected product name (e.g., "Lip Liner")
            expected_color: Expected color/shade (e.g., "#1 On the Rose")
            expected_size: Expected size (e.g., "30ml")

        Returns:
            ImageVerificationResult with verification status
        """
        if not await self.is_available():
            return ImageVerificationResult(
                is_verified=False,
                confidence=0,
                brand_detected=False,
                product_detected=False,
                reasoning="Image verification service not available",
            )

        if not image_url:
            return ImageVerificationResult(
                is_verified=False,
                confidence=0,
                brand_detected=False,
                product_detected=False,
                reasoning="No image URL provided",
            )

        try:
            response = await self.client.post(
                f"{self.base_url}/verify-image",
                json={
                    "image_url": image_url,
                    "expected_brand": expected_brand,
                    "expected_product": expected_product,
                    "expected_color": expected_color,
                    "expected_size": expected_size,
                },
            )

            if response.status_code != 200:
                return ImageVerificationResult(
                    is_verified=False,
                    confidence=0,
                    brand_detected=False,
                    product_detected=False,
                    reasoning=f"Image service error: {response.status_code}",
                )

            data = response.json()
            verification = data.get("verification", {})

            return ImageVerificationResult(
                is_verified=verification.get("is_verified", False),
                confidence=verification.get("confidence", 0),
                brand_detected=verification.get("brand_detected", False),
                product_detected=verification.get("product_detected", False),
                reasoning=verification.get("reasoning", "Unknown"),
                raw_scores=data.get("raw_scores"),
            )

        except httpx.TimeoutException:
            return ImageVerificationResult(
                is_verified=False,
                confidence=0,
                brand_detected=False,
                product_detected=False,
                reasoning="Image verification timed out (model may be loading)",
            )
        except Exception as e:
            return ImageVerificationResult(
                is_verified=False,
                confidence=0,
                brand_detected=False,
                product_detected=False,
                reasoning=f"Image verification failed: {str(e)}",
            )

    async def extract_product_type(self, text: str) -> Dict[str, Any]:
        """
        Extract product type from text using zero-shot classification.

        Args:
            text: Product title or description

        Returns:
            Dict with product_type and is_gift_set info
        """
        if not await self.is_available():
            return {"error": "Service not available"}

        try:
            response = await self.client.post(
                f"{self.base_url}/extract-attributes", json={"text": text}
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Service error: {response.status_code}"}

        except Exception as e:
            return {"error": str(e)}

    async def preload_models(self) -> bool:
        """
        Pre-load models to speed up first verification.

        Call this on app startup.
        """
        if not await self.is_available():
            return False

        try:
            response = await self.client.post(f"{self.base_url}/preload")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


# Global instance
image_client = ImageVerificationClient()
