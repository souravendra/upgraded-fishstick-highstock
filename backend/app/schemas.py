"""
Pydantic schemas for request/response validation.
"""
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, field_validator


class ProductInput(BaseModel):
    """Input schema for product enrichment request."""
    
    name: str = Field(..., min_length=1, max_length=500, description="Product name")
    upc: str = Field(..., min_length=8, max_length=13, description="UPC code")
    brand_name: str = Field(..., min_length=1, max_length=255, description="Brand name")
    size: Optional[str] = Field(None, max_length=100, description="Product size (e.g., '30ml', '1 fl oz')")
    color: Optional[str] = Field(None, max_length=100, description="Product color/shade (e.g., '#190', 'On the Rose')")
    
    @field_validator('upc')
    @classmethod
    def validate_upc(cls, v: str) -> str:
        """Validate UPC format (digits only)."""
        if not v.isdigit():
            raise ValueError('UPC must contain only digits')
        if len(v) not in [8, 12, 13]:  # UPC-A (12), UPC-E (8), EAN-13 (13)
            raise ValueError('UPC must be 8, 12, or 13 digits')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "No Pressure Lip Liner - #1 - On the Rose",
                "upc": "850029397809",
                "brand_name": "DIBS Beauty",
                "size": None,
                "color": "#1 - On the Rose"
            }
        }


class CrawlSource(BaseModel):
    """Information about a source that provided data."""
    
    name: str = Field(..., description="Source name (e.g., 'sephora', 'ulta')")
    url: Optional[str] = Field(None, description="URL where data was found")
    found_upc: bool = Field(..., description="Whether UPC was found on this source")


class VerificationInfo(BaseModel):
    """
    Verification details for product matching.
    
    Critical for ensuring exact matches:
    - Same brand
    - Same size/volume
    - Same color/shade
    """
    
    is_exact_match: bool = Field(..., description="Whether this is a verified exact match")
    brand_match: bool = Field(..., description="Whether brand name matches")
    size_match: bool = Field(..., description="Whether size/volume matches")
    color_match: bool = Field(..., description="Whether color/shade matches")
    mismatches: List[str] = Field(default_factory=list, description="List of mismatched attributes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_exact_match": True,
                "brand_match": True,
                "size_match": True,
                "color_match": True,
                "mismatches": []
            }
        }


class ImageVerificationInfo(BaseModel):
    """
    Image verification details using AI (Transformers.js/CLIP).
    
    Verifies that the product image matches the expected product visually.
    """
    
    is_verified: bool = Field(..., description="Whether image was verified to match")
    confidence: int = Field(..., ge=0, le=100, description="Image match confidence (0-100)")
    brand_detected: bool = Field(..., description="Whether brand was detected in image")
    product_detected: bool = Field(..., description="Whether product type was detected")
    reasoning: str = Field(..., description="Explanation of image verification")
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_verified": True,
                "confidence": 85,
                "brand_detected": True,
                "product_detected": True,
                "reasoning": "Image matches 'DIBS Beauty Lip Liner' with 85% confidence"
            }
        }


class ProductOutput(BaseModel):
    """Output schema for enriched product data."""
    
    # Input data (echoed back)
    upc: str
    brand: str
    product_name: str
    size: Optional[str]
    color: Optional[str]
    
    # Enriched data (the 3 required outputs)
    msrp: Optional[float] = Field(None, description="Manufacturer's suggested retail price")
    image_url: Optional[str] = Field(None, description="Product image URL")
    description: Optional[str] = Field(None, description="Brief product description")
    
    # Metadata
    confidence_score: int = Field(..., ge=0, le=100, description="Confidence score (0-100)")
    reasoning: str = Field(..., description="Explanation of confidence score and verification status")
    sources: List[CrawlSource] = Field(..., description="Sources that provided data")
    
    # Verification (critical requirement!)
    verification: Optional[VerificationInfo] = Field(
        None, 
        description="Verification details showing brand/size/color match status"
    )
    
    # Image verification (AI-powered using Transformers.js/CLIP)
    image_verification: Optional[ImageVerificationInfo] = Field(
        None,
        description="AI-powered image verification using CLIP model"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "upc": "850029397809",
                "brand": "DIBS Beauty",
                "product_name": "No Pressure Lip Liner - #1 - On the Rose",
                "size": None,
                "color": "#1 - On the Rose",
                "msrp": 16.00,
                "image_url": "https://example.com/image.jpg",
                "description": "A smooth, long-lasting lip liner",
                "confidence_score": 95,
                "reasoning": "VERIFIED: Exact match confirmed on 2 source(s) - brand, size, color/shade confirmed",
                "sources": [
                    {"name": "sephora", "url": "https://sephora.com/...", "found_upc": True},
                    {"name": "ulta", "url": "https://ulta.com/...", "found_upc": True}
                ],
                "verification": {
                    "is_exact_match": True,
                    "brand_match": True,
                    "size_match": True,
                    "color_match": True,
                    "mismatches": []
                }
            }
        }


class ErrorResponse(BaseModel):
    """Error response schema."""
    
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
