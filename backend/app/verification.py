"""
Product verification module.

Ensures crawled products match the input exactly:
- Same brand
- Same size/volume
- Same color/shade

This is critical for wholesale buyers who need exact SKU matches.
"""

import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class ExtractedAttributes:
    """Attributes extracted from a product title/description."""

    brand: Optional[str] = None
    size: Optional[str] = None
    size_normalized: Optional[float] = None  # In ml
    color: Optional[str] = None
    shade_number: Optional[str] = None
    is_gift_set: bool = False
    piece_count: Optional[int] = None


@dataclass
class VerificationResult:
    """Result of verifying a product match."""

    is_exact_match: bool
    confidence: int  # 0-100
    brand_match: bool
    size_match: bool
    color_match: bool
    mismatches: List[str]
    reasoning: str


class ProductVerifier:
    """
    Verifies that crawled products match input attributes exactly.

    Uses rule-based extraction for:
    - Size/volume patterns (30ml, 1 fl oz, etc.)
    - Color/shade patterns (#190, Shade 190, etc.)
    - Brand name matching
    - Gift set detection
    """

    # Size patterns and conversions
    SIZE_PATTERNS = [
        # Metric
        (r"(\d+(?:\.\d+)?)\s*ml\b", "ml", 1.0),
        (r"(\d+(?:\.\d+)?)\s*g\b", "g", 1.0),
        (r"(\d+(?:\.\d+)?)\s*oz\b", "oz", 29.5735),  # Convert to ml
        (r"(\d+(?:\.\d+)?)\s*fl\.?\s*oz\b", "fl oz", 29.5735),
        (r"(\d+(?:\.\d+)?)\s*L\b", "L", 1000.0),  # Convert to ml
        # Count-based
        (r"(\d+)\s*(?:pairs?|pcs?|pieces?|count)\b", "count", None),
        (r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(ml|g|oz)", "pack", None),
    ]

    # Color/shade patterns
    COLOR_PATTERNS = [
        r"#(\d+)",  # #190, #1
        r"shade\s*[#:]?\s*(\d+)",  # Shade 190, Shade: 190
        r"shade\s*[#:]?\s*([a-zA-Z0-9\s\-]+)",  # Shade: On the Rose
        r"color\s*[#:]?\s*([a-zA-Z0-9\s\-]+)",  # Color: Red
        r"-\s*#(\d+)\s*-",  # - #1 -
        r"in\s+([a-zA-Z0-9\s]+)\s*$",  # "in shade 190"
    ]

    # Gift set indicators
    GIFT_SET_PATTERNS = [
        r"\bgift\s*set\b",
        r"\bset\b",
        r"\bkit\b",
        r"\bduo\b",
        r"\btrio\b",
        r"(\d+)\s*(?:pc|piece|pcs)",
    ]

    def extract_attributes(self, text: str) -> ExtractedAttributes:
        """
        Extract product attributes from title/description text.

        Args:
            text: Product title or description

        Returns:
            ExtractedAttributes with parsed values
        """
        if not text:
            return ExtractedAttributes()

        text_lower = text.lower()

        # Extract size
        size, size_normalized = self._extract_size(text_lower)

        # Extract color/shade
        color, shade_number = self._extract_color(text)

        # Check for gift set
        is_gift_set, piece_count = self._detect_gift_set(text_lower)

        return ExtractedAttributes(
            brand=None,  # Brand extracted separately
            size=size,
            size_normalized=size_normalized,
            color=color,
            shade_number=shade_number,
            is_gift_set=is_gift_set,
            piece_count=piece_count,
        )

    def _extract_size(self, text: str) -> Tuple[Optional[str], Optional[float]]:
        """Extract size/volume from text."""
        for pattern, unit, multiplier in self.SIZE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                original = match.group(0)

                if multiplier is not None:
                    try:
                        normalized = float(value) * multiplier
                        return original, normalized
                    except ValueError:
                        pass

                return original, None

        return None, None

    def _extract_color(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract color/shade from text."""
        for pattern in self.COLOR_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()

                # Check if it's a number (shade number)
                if value.isdigit():
                    return None, value
                else:
                    return value, None

        return None, None

    def _detect_gift_set(self, text: str) -> Tuple[bool, Optional[int]]:
        """Detect if product is a gift set and extract piece count."""
        for pattern in self.GIFT_SET_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Try to extract piece count
                if match.lastindex and match.group(1).isdigit():
                    return True, int(match.group(1))
                return True, None

        return False, None

    def verify_match(
        self,
        input_brand: str,
        input_name: str,
        input_size: Optional[str],
        input_color: Optional[str],
        found_title: Optional[str],
        found_description: Optional[str],
        found_upc_match: bool = False,  # NEW: Did UPC match from source?
    ) -> VerificationResult:
        """
        Verify if a found product matches the input exactly.

        CRITICAL: If UPC matched from a reliable source, trust it!
        UPC is the authoritative identifier.

        Args:
            input_brand: Expected brand name
            input_name: Expected product name
            input_size: Expected size (optional)
            input_color: Expected color/shade (optional)
            found_title: Title from crawled product
            found_description: Description from crawled product
            found_upc_match: Whether UPC was found on the source (authoritative!)

        Returns:
            VerificationResult with match status and confidence
        """
        mismatches: List[str] = []

        # Normalize "null" strings to None
        input_size = None if input_size in (None, "null", "None", "") else input_size
        input_color = None if input_color in (None, "null", "None", "") else input_color

        # Combine found text for analysis
        found_text = f"{found_title or ''} {found_description or ''}".strip()

        if not found_text:
            # No text but UPC matched - still trust it!
            if found_upc_match:
                return VerificationResult(
                    is_exact_match=True,
                    confidence=85,
                    brand_match=True,  # Trust UPC
                    size_match=True,
                    color_match=True,
                    mismatches=[],
                    reasoning="UPC matched - product verified by barcode",
                )
            return VerificationResult(
                is_exact_match=False,
                confidence=0,
                brand_match=False,
                size_match=False,
                color_match=False,
                mismatches=["No product information found"],
                reasoning="No product title or description available",
            )

        # Extract attributes from found product
        found_attrs = self.extract_attributes(found_text)
        input_attrs = self.extract_attributes(
            f"{input_name} {input_size or ''} {input_color or ''}"
        )

        # 1. Verify brand
        brand_match = self._verify_brand(input_brand, found_text)
        if not brand_match:
            mismatches.append(f"Brand mismatch: expected '{input_brand}'")

        # 2. Verify size (if provided)
        size_match = True
        if input_size:
            size_match = self._verify_size(input_attrs, found_attrs)
            if not size_match:
                mismatches.append(
                    f"Size mismatch: expected '{input_size}', found '{found_attrs.size}'"
                )

        # 3. Verify color/shade (if provided)
        color_match = True
        if input_color:
            color_match = self._verify_color(input_color, input_attrs, found_attrs)
            if not color_match:
                expected_color = (
                    input_color or input_attrs.color or input_attrs.shade_number
                )
                found_color = found_attrs.color or found_attrs.shade_number
                mismatches.append(
                    f"Color/shade mismatch: expected '{expected_color}', found '{found_color}'"
                )

        # CRITICAL: If UPC matched, be more lenient!
        # UPC is authoritative - attribute extraction can be flaky
        if found_upc_match:
            if brand_match:
                # Brand matches + UPC matches = HIGH confidence
                # Size/color mismatches might be extraction errors
                is_exact_match = True
                confidence = 90 if (size_match and color_match) else 80
                reasoning = "UPC verified" + (
                    f" (note: {'; '.join(mismatches)})" if mismatches else ""
                )
                return VerificationResult(
                    is_exact_match=is_exact_match,
                    confidence=confidence,
                    brand_match=brand_match,
                    size_match=size_match,
                    color_match=color_match,
                    mismatches=mismatches if not (size_match and color_match) else [],
                    reasoning=reasoning,
                )

        # No UPC match - rely on attribute verification
        is_exact_match = brand_match and size_match and color_match
        confidence = self._calculate_confidence(
            brand_match, size_match, color_match, input_size, input_color
        )
        reasoning = self._build_reasoning(
            brand_match, size_match, color_match, mismatches
        )

        return VerificationResult(
            is_exact_match=is_exact_match,
            confidence=confidence,
            brand_match=brand_match,
            size_match=size_match,
            color_match=color_match,
            mismatches=mismatches,
            reasoning=reasoning,
        )

    def _verify_brand(self, expected_brand: str, found_text: str) -> bool:
        """Verify brand name matches."""
        expected_lower = expected_brand.lower().strip()
        found_lower = found_text.lower()

        # Direct match
        if expected_lower in found_lower:
            return True

        # Handle common variations
        brand_variations = self._get_brand_variations(expected_lower)
        for variation in brand_variations:
            if variation in found_lower:
                return True

        return False

    def _get_brand_variations(self, brand: str) -> List[str]:
        """Get common variations of a brand name."""
        variations = [brand]

        # Remove common suffixes/prefixes
        variations.append(brand.replace(" beauty", ""))
        variations.append(brand.replace("the ", ""))

        # Handle special characters
        variations.append(brand.replace("&", "and"))
        variations.append(brand.replace(" and ", " & "))

        # Handle spacing
        variations.append(brand.replace(" ", ""))
        variations.append(brand.replace("-", " "))
        variations.append(brand.replace("-", ""))

        return variations

    def _verify_size(
        self, input_attrs: ExtractedAttributes, found_attrs: ExtractedAttributes
    ) -> bool:
        """Verify size/volume matches."""
        # If both have normalized sizes, compare them
        if input_attrs.size_normalized and found_attrs.size_normalized:
            # Allow 5% tolerance for rounding differences
            tolerance = 0.05
            ratio = input_attrs.size_normalized / found_attrs.size_normalized
            return 1 - tolerance <= ratio <= 1 + tolerance

        # If both have raw sizes, compare strings
        if input_attrs.size and found_attrs.size:
            input_size = re.sub(r"[^\d.]", "", input_attrs.size)
            found_size = re.sub(r"[^\d.]", "", found_attrs.size)
            return input_size == found_size

        # If input has size but found doesn't, can't verify
        if input_attrs.size and not found_attrs.size:
            return False

        # If input has no size requirement, consider it a match
        return True

    def _verify_color(
        self,
        input_color: Optional[str],
        input_attrs: ExtractedAttributes,
        found_attrs: ExtractedAttributes,
    ) -> bool:
        """Verify color/shade matches."""
        # Get expected values
        expected_shade = input_attrs.shade_number
        expected_color = input_color or input_attrs.color

        # Extract from input_color string if provided
        if input_color:
            # Check if input_color contains a shade number
            shade_match = re.search(r"#?(\d+)", input_color)
            if shade_match:
                expected_shade = shade_match.group(1)
            else:
                expected_color = input_color

        # Compare shade numbers (exact match required)
        if expected_shade and found_attrs.shade_number:
            return expected_shade == found_attrs.shade_number

        # Compare color names (fuzzy match)
        if expected_color and found_attrs.color:
            return self._fuzzy_color_match(expected_color, found_attrs.color)

        # If we have expected but not found, can't verify
        if (expected_shade or expected_color) and not (
            found_attrs.shade_number or found_attrs.color
        ):
            return False

        # If no color requirement, consider it a match
        return True

    def _fuzzy_color_match(self, expected: str, found: str) -> bool:
        """Fuzzy match color names."""
        expected_lower = expected.lower().strip()
        found_lower = found.lower().strip()

        # Direct match
        if expected_lower == found_lower:
            return True

        # One contains the other
        if expected_lower in found_lower or found_lower in expected_lower:
            return True

        # Remove common words and compare
        stop_words = ["the", "in", "shade", "color", "-", "#"]
        for word in stop_words:
            expected_lower = expected_lower.replace(word, " ")
            found_lower = found_lower.replace(word, " ")

        expected_clean = " ".join(expected_lower.split())
        found_clean = " ".join(found_lower.split())

        return expected_clean == found_clean

    def _calculate_confidence(
        self,
        brand_match: bool,
        size_match: bool,
        color_match: bool,
        input_size: Optional[str],
        input_color: Optional[str],
    ) -> int:
        """Calculate confidence score based on matches."""

        # Brand is always required
        if not brand_match:
            return 20  # Very low confidence

        base_confidence = 60  # Brand matched

        # Size verification
        if input_size:
            if size_match:
                base_confidence += 20
            else:
                base_confidence -= 30  # Major penalty for size mismatch
        else:
            base_confidence += 10  # No size to verify, slight boost

        # Color verification
        if input_color:
            if color_match:
                base_confidence += 20
            else:
                base_confidence -= 30  # Major penalty for color mismatch
        else:
            base_confidence += 10  # No color to verify, slight boost

        return max(0, min(100, base_confidence))

    def _build_reasoning(
        self,
        brand_match: bool,
        size_match: bool,
        color_match: bool,
        mismatches: List[str],
    ) -> str:
        """Build human-readable reasoning."""
        if not mismatches:
            matches = []
            if brand_match:
                matches.append("brand")
            if size_match:
                matches.append("size")
            if color_match:
                matches.append("color/shade")
            return f"Exact match verified: {', '.join(matches)} confirmed"
        else:
            return f"Verification failed: {'; '.join(mismatches)}"


# Global instance
product_verifier = ProductVerifier()
