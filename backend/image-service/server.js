/**
 * Image Verification Service using Transformers.js
 * 
 * Uses CLIP model to:
 * 1. Compare product image to expected description
 * 2. Verify color/shade visually
 * 3. Detect gift sets vs single products
 * 
 * Runs locally - no API costs!
 */

import express from 'express';
import cors from 'cors';
import { pipeline, env } from '@xenova/transformers';

// Configure Transformers.js
env.cacheDir = './.cache';
env.allowLocalModels = true;

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.PORT || 3001;

// Model instances (lazy loaded)
let clipModel = null;
let zeroShotClassifier = null;

/**
 * Load CLIP model for image-text similarity
 */
async function getClipModel() {
    if (!clipModel) {
        console.log('🔄 Loading CLIP model (first time only)...');
        clipModel = await pipeline(
            'zero-shot-image-classification',
            'Xenova/clip-vit-base-patch32'
        );
        console.log('✅ CLIP model loaded');
    }
    return clipModel;
}

/**
 * Load zero-shot text classifier for attribute extraction
 */
async function getTextClassifier() {
    if (!zeroShotClassifier) {
        console.log('🔄 Loading text classifier...');
        zeroShotClassifier = await pipeline(
            'zero-shot-classification',
            'Xenova/mobilebert-uncased-mnli'
        );
        console.log('✅ Text classifier loaded');
    }
    return zeroShotClassifier;
}

/**
 * Health check endpoint
 */
app.get('/health', (req, res) => {
    res.json({ 
        status: 'ok', 
        service: 'Image Verification Service',
        models: {
            clip: clipModel ? 'loaded' : 'not loaded',
            textClassifier: zeroShotClassifier ? 'loaded' : 'not loaded'
        }
    });
});

/**
 * Verify image matches product description
 * 
 * POST /verify-image
 * Body: {
 *   image_url: "https://...",
 *   expected_brand: "DIBS Beauty",
 *   expected_product: "Lip Liner",
 *   expected_color: "#1 On the Rose",
 *   expected_size: "30ml"
 * }
 */
app.post('/verify-image', async (req, res) => {
    try {
        const { 
            image_url, 
            expected_brand, 
            expected_product,
            expected_color,
            expected_size 
        } = req.body;

        if (!image_url) {
            return res.status(400).json({ error: 'image_url is required' });
        }

        console.log(`\n🔍 Verifying image: ${image_url}`);
        console.log(`   Expected: ${expected_brand} ${expected_product}`);
        if (expected_color) console.log(`   Color: ${expected_color}`);
        if (expected_size) console.log(`   Size: ${expected_size}`);

        const model = await getClipModel();

        // Build candidate descriptions
        const candidates = buildCandidateDescriptions(
            expected_brand,
            expected_product,
            expected_color,
            expected_size
        );

        console.log(`   Candidates: ${JSON.stringify(candidates)}`);

        // Run CLIP classification
        const results = await model(image_url, candidates);

        console.log(`   Results:`, results);

        // Analyze results
        const analysis = analyzeClipResults(results, expected_brand, expected_product, expected_color);

        res.json({
            success: true,
            image_url,
            verification: analysis,
            raw_scores: results
        });

    } catch (error) {
        console.error('❌ Error verifying image:', error);
        res.status(500).json({ 
            error: 'Failed to verify image',
            detail: error.message 
        });
    }
});

/**
 * Compare two images for similarity (e.g., compare crawled image to reference)
 * 
 * POST /compare-images
 * Body: {
 *   image1_url: "https://...",
 *   image2_url: "https://..."
 * }
 */
app.post('/compare-images', async (req, res) => {
    try {
        const { image1_url, image2_url } = req.body;

        if (!image1_url || !image2_url) {
            return res.status(400).json({ error: 'Both image URLs are required' });
        }

        const model = await getClipModel();

        // Use the same product description for both, check if they match similarly
        const testDescription = ['a beauty product', 'cosmetics', 'skincare product'];
        
        const results1 = await model(image1_url, testDescription);
        const results2 = await model(image2_url, testDescription);

        // Calculate similarity based on distribution
        const similarity = calculateDistributionSimilarity(results1, results2);

        res.json({
            success: true,
            similarity_score: similarity,
            are_similar: similarity > 0.8,
            image1_classification: results1,
            image2_classification: results2
        });

    } catch (error) {
        console.error('❌ Error comparing images:', error);
        res.status(500).json({ 
            error: 'Failed to compare images',
            detail: error.message 
        });
    }
});

/**
 * Extract product attributes from text using zero-shot classification
 * 
 * POST /extract-attributes
 * Body: {
 *   text: "Fenty Beauty Pro Filt'r Foundation 30ml Shade 190"
 * }
 */
app.post('/extract-attributes', async (req, res) => {
    try {
        const { text } = req.body;

        if (!text) {
            return res.status(400).json({ error: 'text is required' });
        }

        const classifier = await getTextClassifier();

        // Classify product type
        const productTypes = ['lipstick', 'foundation', 'mascara', 'lip liner', 'eyeshadow', 'skincare', 'fragrance', 'gift set'];
        const productResult = await classifier(text, productTypes);

        // Classify if it's a set or single item
        const setTypes = ['single product', 'gift set', 'travel set', 'bundle'];
        const setResult = await classifier(text, setTypes);

        res.json({
            success: true,
            text,
            product_type: {
                label: productResult.labels[0],
                confidence: productResult.scores[0]
            },
            is_set: {
                label: setResult.labels[0],
                confidence: setResult.scores[0],
                is_gift_set: setResult.labels[0].includes('set') || setResult.labels[0].includes('bundle')
            },
            all_product_scores: Object.fromEntries(
                productResult.labels.map((l, i) => [l, productResult.scores[i]])
            )
        });

    } catch (error) {
        console.error('❌ Error extracting attributes:', error);
        res.status(500).json({ 
            error: 'Failed to extract attributes',
            detail: error.message 
        });
    }
});

/**
 * Pre-load models on startup (optional, for faster first request)
 * 
 * POST /preload
 */
app.post('/preload', async (req, res) => {
    try {
        console.log('⏳ Pre-loading models...');
        await getClipModel();
        await getTextClassifier();
        res.json({ success: true, message: 'Models pre-loaded' });
    } catch (error) {
        res.status(500).json({ error: 'Failed to pre-load models', detail: error.message });
    }
});

// ============ Helper Functions ============

/**
 * Build candidate descriptions for CLIP classification
 */
function buildCandidateDescriptions(brand, product, color, size) {
    const candidates = [];

    // Exact match description
    let exact = `${brand} ${product}`;
    if (color) exact += ` ${color}`;
    if (size) exact += ` ${size}`;
    candidates.push(exact);

    // Brand only
    candidates.push(`${brand} beauty product`);

    // Wrong brand (for comparison)
    candidates.push('generic beauty product');
    candidates.push('unknown brand cosmetic');

    // Different product type (to check for mix-ups)
    if (product.toLowerCase().includes('lip')) {
        candidates.push(`${brand} foundation`);
        candidates.push(`${brand} mascara`);
    } else if (product.toLowerCase().includes('foundation')) {
        candidates.push(`${brand} lipstick`);
        candidates.push(`${brand} mascara`);
    }

    return candidates;
}

/**
 * Analyze CLIP results and determine if image matches expected product
 */
function analyzeClipResults(results, expectedBrand, expectedProduct, expectedColor) {
    // Results are sorted by score (highest first)
    const topResult = results[0];
    const topScore = topResult.score;
    const topLabel = topResult.label;

    // Check if top result matches expected
    const expectedLower = `${expectedBrand} ${expectedProduct}`.toLowerCase();
    const topLabelLower = topLabel.toLowerCase();

    const brandMatch = topLabelLower.includes(expectedBrand.toLowerCase());
    const productMatch = topLabelLower.includes(expectedProduct.toLowerCase().split(' ')[0]);

    // Calculate confidence
    let confidence = 0;
    let isMatch = false;

    if (brandMatch && productMatch && topScore > 0.3) {
        confidence = Math.min(95, Math.round(topScore * 100 + 30));
        isMatch = true;
    } else if (brandMatch && topScore > 0.25) {
        confidence = Math.min(75, Math.round(topScore * 100 + 15));
        isMatch = topScore > 0.35;
    } else if (topScore > 0.4) {
        confidence = Math.round(topScore * 100);
        isMatch = false; // High score but wrong product
    } else {
        confidence = Math.round(topScore * 100);
        isMatch = false;
    }

    return {
        is_verified: isMatch,
        confidence,
        best_match: topLabel,
        best_score: topScore,
        brand_detected: brandMatch,
        product_detected: productMatch,
        reasoning: isMatch 
            ? `Image matches "${expectedBrand} ${expectedProduct}" with ${confidence}% confidence`
            : `Image may not match expected product. Best match: "${topLabel}" (${Math.round(topScore * 100)}%)`
    };
}

/**
 * Calculate similarity between two classification distributions
 */
function calculateDistributionSimilarity(results1, results2) {
    // Simple cosine similarity of score distributions
    const scores1 = results1.map(r => r.score);
    const scores2 = results2.map(r => r.score);

    let dotProduct = 0;
    let norm1 = 0;
    let norm2 = 0;

    for (let i = 0; i < scores1.length; i++) {
        dotProduct += scores1[i] * scores2[i];
        norm1 += scores1[i] * scores1[i];
        norm2 += scores2[i] * scores2[i];
    }

    return dotProduct / (Math.sqrt(norm1) * Math.sqrt(norm2));
}

// Start server
app.listen(PORT, () => {
    console.log(`
🖼️  Image Verification Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Running on: http://localhost:${PORT}
    
Endpoints:
  GET  /health           - Health check
  POST /verify-image     - Verify image matches product
  POST /compare-images   - Compare two images
  POST /extract-attributes - Extract product attributes from text
  POST /preload          - Pre-load models

Note: First request will download models (~400MB).
      Subsequent requests will be fast.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    `);
});
