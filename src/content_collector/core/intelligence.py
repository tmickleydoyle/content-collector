"""
Intelligent content analysis and AI-powered features for world-class web scraping.
"""

import json
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import structlog
from selectolax.parser import HTMLParser

logger = structlog.get_logger()

# Optional AI/ML imports
try:
    import nltk
    from nltk.chunk import ne_chunk
    from nltk.corpus import stopwords
    from nltk.tag import pos_tag
    from nltk.tokenize import sent_tokenize, word_tokenize

    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    import textstat

    TEXTSTAT_AVAILABLE = True
except ImportError:
    TEXTSTAT_AVAILABLE = False


class ContentIntelligence:
    """Advanced intelligent analysis of scraped content."""

    def __init__(self):
        """Initialize content intelligence analyzer."""
        self.logger = logger.bind(component="content_intelligence")

        # Initialize NLTK data if available
        if NLTK_AVAILABLE:
            try:
                nltk.data.find("tokenizers/punkt")
                nltk.data.find("corpora/stopwords")
                nltk.data.find("taggers/averaged_perceptron_tagger")
                nltk.data.find("chunkers/maxent_ne_chunker")
                nltk.data.find("corpora/words")
            except LookupError:
                # Download required NLTK data silently
                try:
                    nltk.download("punkt", quiet=True)
                    nltk.download("stopwords", quiet=True)
                    nltk.download("averaged_perceptron_tagger", quiet=True)
                    nltk.download("maxent_ne_chunker", quiet=True)
                    nltk.download("words", quiet=True)
                except:
                    self.logger.warning("Failed to download NLTK data")

    def analyze_content(self, parsed_data: Dict) -> Dict:
        """
        Perform comprehensive intelligent analysis of parsed content.

        Args:
            parsed_data: Parsed content from ContentParser

        Returns:
            Dictionary with intelligent analysis results
        """
        analysis = {
            "content_quality": self._analyze_content_quality(parsed_data),
            "semantic_analysis": self._analyze_semantics(parsed_data),
            "link_intelligence": self._analyze_links(parsed_data),
            "structural_analysis": self._analyze_structure(parsed_data),
            "technology_stack": self._detect_technology_stack(parsed_data),
            "content_classification": self._classify_content(parsed_data),
            "extraction_insights": self._generate_insights(parsed_data),
        }

        return analysis

    def _analyze_content_quality(self, parsed_data: Dict) -> Dict:
        """Analyze the quality and readability of content."""
        body_text = parsed_data.get("body_text", "")

        quality = {
            "word_count": len(body_text.split()) if body_text else 0,
            "character_count": len(body_text),
            "sentence_count": 0,
            "readability_scores": {},
            "content_density": 0.0,
            "quality_score": 0.0,
        }

        if not body_text:
            return quality

        # Sentence analysis
        if NLTK_AVAILABLE:
            try:
                sentences = sent_tokenize(body_text)
                quality["sentence_count"] = len(sentences)
                quality["avg_sentence_length"] = quality["word_count"] / max(
                    len(sentences), 1
                )
            except:
                quality["sentence_count"] = len(re.split(r"[.!?]+", body_text))
        else:
            quality["sentence_count"] = len(re.split(r"[.!?]+", body_text))

        # Readability analysis
        if TEXTSTAT_AVAILABLE:
            try:
                quality["readability_scores"] = {
                    "flesch_reading_ease": textstat.flesch_reading_ease(body_text),
                    "flesch_kincaid_grade": textstat.flesch_kincaid_grade(body_text),
                    "gunning_fog": textstat.gunning_fog(body_text),
                    "automated_readability_index": textstat.automated_readability_index(
                        body_text
                    ),
                }
            except:
                pass

        # Content density (meaningful content vs total HTML)
        html_length = parsed_data.get("content_length", 0)
        if html_length > 0:
            quality["content_density"] = len(body_text) / html_length

        # Overall quality score (0-100)
        quality["quality_score"] = self._calculate_quality_score(quality, parsed_data)

        return quality

    def _analyze_semantics(self, parsed_data: Dict) -> Dict:
        """Analyze semantic content of the page."""
        body_text = parsed_data.get("body_text", "")
        title = parsed_data.get("title", "")

        semantics = {
            "key_topics": [],
            "entities": [],
            "keywords": [],
            "sentiment": "neutral",
            "language": "unknown",
            "content_themes": [],
        }

        if not body_text:
            return semantics

        # Keyword extraction
        semantics["keywords"] = self._extract_keywords(body_text)

        # Topic detection
        semantics["key_topics"] = self._detect_topics(body_text, title)

        # Named entity recognition
        if NLTK_AVAILABLE:
            try:
                semantics["entities"] = self._extract_entities(body_text)
            except:
                pass

        # Content themes
        semantics["content_themes"] = self._identify_themes(body_text, parsed_data)

        return semantics

    def _analyze_links(self, parsed_data: Dict) -> Dict:
        """Intelligent analysis of discovered links."""
        links = parsed_data.get("links", [])

        analysis = {
            "total_links": len(links),
            "internal_links": 0,
            "external_links": 0,
            "domain_distribution": {},
            "link_types": {},
            "social_links": [],
            "resource_links": {},
            "navigation_patterns": [],
            "link_quality_score": 0.0,
        }

        if not links:
            return analysis

        # Categorize links
        social_domains = {
            "twitter.com",
            "x.com",
            "facebook.com",
            "linkedin.com",
            "instagram.com",
            "youtube.com",
            "github.com",
            "gitlab.com",
            "discord.com",
            "reddit.com",
        }

        resource_patterns = {
            "documentation": r"(docs?|documentation|guide|tutorial|help)",
            "api": r"(api|rest|graphql|endpoint)",
            "blog": r"(blog|article|post|news)",
            "download": r"(download|release|dist|cdn)",
            "contact": r"(contact|about|support|team)",
        }

        for link in links:
            try:
                parsed_url = urlparse(link)
                domain = parsed_url.netloc.lower()

                # Count domains
                analysis["domain_distribution"][domain] = (
                    analysis["domain_distribution"].get(domain, 0) + 1
                )

                # Internal vs external
                # Note: We don't have the source domain here, so we'll count unique domains
                if len(analysis["domain_distribution"]) == 1:
                    analysis["internal_links"] += 1
                else:
                    analysis["external_links"] += 1

                # Social links
                if any(social in domain for social in social_domains):
                    analysis["social_links"].append(link)

                # Resource categorization
                full_url = link.lower()
                for category, pattern in resource_patterns.items():
                    if re.search(pattern, full_url, re.IGNORECASE):
                        if category not in analysis["resource_links"]:
                            analysis["resource_links"][category] = []
                        analysis["resource_links"][category].append(link)

            except:
                continue

        # Calculate link quality score
        analysis["link_quality_score"] = self._calculate_link_quality(analysis)

        return analysis

    def _analyze_structure(self, parsed_data: Dict) -> Dict:
        """Analyze the structural quality of the page."""
        headers = parsed_data.get("headers", {})
        head_html = parsed_data.get("head_html", "")

        structure = {
            "heading_structure": {},
            "seo_analysis": {},
            "accessibility_score": 0.0,
            "meta_completeness": 0.0,
            "schema_markup": [],
            "performance_hints": [],
        }

        # Heading hierarchy analysis
        structure["heading_structure"] = {
            "h1_count": len(headers.get("h1", [])),
            "h2_count": len(headers.get("h2", [])),
            "h3_count": len(headers.get("h3", [])),
            "hierarchy_score": self._score_heading_hierarchy(headers),
            "missing_levels": self._find_missing_heading_levels(headers),
        }

        # SEO analysis
        structure["seo_analysis"] = self._analyze_seo(parsed_data)

        # Schema markup detection
        if head_html:
            structure["schema_markup"] = self._extract_schema_markup(head_html)

        # Performance hints from head
        if head_html:
            structure["performance_hints"] = self._analyze_performance_hints(head_html)

        return structure

    def _detect_technology_stack(self, parsed_data: Dict) -> Dict:
        """Detect the technology stack used by the website."""
        head_html = parsed_data.get("head_html", "")
        body_text = parsed_data.get("body_text", "")

        tech_stack = {
            "frameworks": [],
            "cms": [],
            "analytics": [],
            "cdn": [],
            "javascript_libraries": [],
            "css_frameworks": [],
            "build_tools": [],
            "hosting_platform": [],
        }

        if not head_html:
            return tech_stack

        # Framework detection patterns
        framework_patterns = {
            "react": r"react|_react|__REACT",
            "vue": r"vue\.js|vuejs|__VUE__",
            "angular": r"angular|ng-app|__ng",
            "nextjs": r"next\.js|_next/|__NEXT_DATA__",
            "nuxt": r"nuxt|__NUXT__",
            "svelte": r"svelte|_svelte",
            "gatsby": r"gatsby|___gatsby",
            "astro": r"astro|_astro",
        }

        cms_patterns = {
            "wordpress": r"wp-content|wp-includes|wordpress",
            "drupal": r"drupal|sites/default",
            "joomla": r"joomla|com_content",
            "shopify": r"shopify|cdn\.shopify",
            "wix": r"wix\.com|wixstatic",
            "squarespace": r"squarespace|sqsp\.net",
        }

        analytics_patterns = {
            "google_analytics": r"google-analytics|gtag|ga\.js",
            "google_tag_manager": r"googletagmanager",
            "facebook_pixel": r"fbevents|facebook\.net",
            "mixpanel": r"mixpanel",
            "amplitude": r"amplitude",
            "hotjar": r"hotjar",
            "segment": r"segment\.com|analytics\.js",
        }

        # Check patterns
        content_to_check = (head_html + body_text).lower()

        for framework, pattern in framework_patterns.items():
            if re.search(pattern, content_to_check, re.IGNORECASE):
                tech_stack["frameworks"].append(framework)

        for cms, pattern in cms_patterns.items():
            if re.search(pattern, content_to_check, re.IGNORECASE):
                tech_stack["cms"].append(cms)

        for analytics, pattern in analytics_patterns.items():
            if re.search(pattern, content_to_check, re.IGNORECASE):
                tech_stack["analytics"].append(analytics)

        return tech_stack

    def _classify_content(self, parsed_data: Dict) -> Dict:
        """Classify the type and purpose of the content."""
        title = parsed_data.get("title", "").lower()
        body_text = parsed_data.get("body_text", "").lower()
        links = parsed_data.get("links", [])

        classification = {
            "content_type": "unknown",
            "industry": "unknown",
            "purpose": "unknown",
            "audience": "general",
            "business_model": "unknown",
            "confidence_score": 0.0,
        }

        # Content type classification
        content_indicators = {
            "blog": ["blog", "article", "post", "author", "published", "comments"],
            "ecommerce": ["shop", "buy", "cart", "price", "product", "checkout"],
            "news": ["news", "breaking", "report", "journalist", "headline"],
            "documentation": ["docs", "api", "guide", "tutorial", "reference"],
            "portfolio": ["portfolio", "work", "project", "design", "showcase"],
            "landing": ["sign up", "get started", "free trial", "demo", "pricing"],
            "corporate": ["about us", "company", "team", "careers", "contact"],
            "social": ["profile", "followers", "posts", "share", "like"],
            "educational": ["course", "learn", "student", "education", "training"],
        }

        # Score each type
        scores = {}
        for content_type, keywords in content_indicators.items():
            score = sum(
                1 for keyword in keywords if keyword in title or keyword in body_text
            )
            if score > 0:
                scores[content_type] = score

        if scores:
            classification["content_type"] = max(scores, key=scores.get)
            classification["confidence_score"] = scores[
                classification["content_type"]
            ] / len(content_indicators[classification["content_type"]])

        return classification

    def _generate_insights(self, parsed_data: Dict) -> List[str]:
        """Generate actionable insights about the scraped content."""
        insights = []

        # Content quality insights
        body_text = parsed_data.get("body_text", "")
        if len(body_text) < 300:
            insights.append(
                "Content is quite short - consider if this page has substantial value"
            )

        # Link insights
        links = parsed_data.get("links", [])
        if len(links) == 0:
            insights.append(
                "No links found - page might be isolated or have navigation issues"
            )
        elif len(links) > 100:
            insights.append(
                "High number of links detected - might indicate navigation-heavy page"
            )

        # Title insights
        title = parsed_data.get("title", "")
        if not title:
            insights.append("Missing page title - critical for SEO")
        elif len(title) < 30:
            insights.append("Title is quite short - consider expanding for better SEO")
        elif len(title) > 60:
            insights.append("Title is long - might be truncated in search results")

        # Headers insights
        headers = parsed_data.get("headers", {})
        if not any(headers.values()):
            insights.append(
                "No heading structure found - content may lack organization"
            )

        # Meta description insights
        meta_desc = parsed_data.get("meta_description", "")
        if not meta_desc:
            insights.append(
                "Missing meta description - opportunity for better search snippets"
            )

        return insights

    # Helper methods
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from text."""
        if not text:
            return []

        # Simple keyword extraction
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

        # Remove stopwords if NLTK available
        if NLTK_AVAILABLE:
            try:
                stop_words = set(stopwords.words("english"))
                words = [word for word in words if word not in stop_words]
            except:
                pass

        # Get most common words
        word_freq = Counter(words)
        return [word for word, count in word_freq.most_common(10)]

    def _detect_topics(self, text: str, title: str) -> List[str]:
        """Detect main topics from content."""
        topics = []

        # Simple topic detection based on keywords
        tech_keywords = [
            "api",
            "software",
            "development",
            "code",
            "programming",
            "technology",
        ]
        business_keywords = [
            "business",
            "company",
            "market",
            "sales",
            "revenue",
            "strategy",
        ]
        design_keywords = ["design", "ui", "ux", "interface", "creative", "visual"]

        text_lower = (text + " " + title).lower()

        if any(keyword in text_lower for keyword in tech_keywords):
            topics.append("technology")
        if any(keyword in text_lower for keyword in business_keywords):
            topics.append("business")
        if any(keyword in text_lower for keyword in design_keywords):
            topics.append("design")

        return topics

    def _extract_entities(self, text: str) -> List[Dict]:
        """Extract named entities from text."""
        if not NLTK_AVAILABLE:
            return []

        entities = []
        try:
            tokens = word_tokenize(text[:1000])  # Limit for performance
            pos_tags = pos_tag(tokens)
            chunks = ne_chunk(pos_tags, binary=False)

            for chunk in chunks:
                if hasattr(chunk, "label"):
                    entity_name = " ".join([token for token, pos in chunk.leaves()])
                    entities.append(
                        {
                            "text": entity_name,
                            "label": chunk.label(),
                            "confidence": 0.8,  # Placeholder confidence
                        }
                    )
        except:
            pass

        return entities[:10]  # Return top 10

    def _identify_themes(self, text: str, parsed_data: Dict) -> List[str]:
        """Identify content themes."""
        themes = []

        # Check for common themes
        if "ai" in text.lower() or "artificial intelligence" in text.lower():
            themes.append("artificial intelligence")
        if "cloud" in text.lower():
            themes.append("cloud computing")
        if "security" in text.lower():
            themes.append("cybersecurity")
        if "data" in text.lower() and (
            "analytics" in text.lower() or "science" in text.lower()
        ):
            themes.append("data science")

        return themes

    def _calculate_quality_score(self, quality: Dict, parsed_data: Dict) -> float:
        """Calculate overall content quality score."""
        score = 0.0

        # Word count score (optimal 300-2000 words)
        word_count = quality.get("word_count", 0)
        if 300 <= word_count <= 2000:
            score += 25
        elif word_count > 2000:
            score += 20
        elif word_count > 100:
            score += 10

        # Title presence
        if parsed_data.get("title"):
            score += 25

        # Meta description presence
        if parsed_data.get("meta_description"):
            score += 15

        # Header structure
        headers = parsed_data.get("headers", {})
        if any(headers.values()):
            score += 15

        # Content density
        density = quality.get("content_density", 0)
        if density > 0.1:
            score += 20

        return min(score, 100.0)

    def _calculate_link_quality(self, analysis: Dict) -> float:
        """Calculate link quality score."""
        score = 0.0

        total_links = analysis.get("total_links", 0)
        if total_links == 0:
            return 0.0

        # Balanced internal/external ratio
        internal = analysis.get("internal_links", 0)
        external = analysis.get("external_links", 0)

        if total_links > 5:
            ratio = (
                min(internal, external) / max(internal, external)
                if max(internal, external) > 0
                else 0
            )
            score += ratio * 50

        # Social presence
        social_count = len(analysis.get("social_links", []))
        if social_count > 0:
            score += min(social_count * 10, 30)

        # Resource diversity
        resource_types = len(analysis.get("resource_links", {}))
        score += min(resource_types * 5, 20)

        return min(score, 100.0)

    def _score_heading_hierarchy(self, headers: Dict) -> float:
        """Score the heading hierarchy quality."""
        h1_count = len(headers.get("h1", []))
        h2_count = len(headers.get("h2", []))
        h3_count = len(headers.get("h3", []))

        score = 0.0

        # Ideal: one H1, multiple H2s, some H3s
        if h1_count == 1:
            score += 40
        elif h1_count == 0:
            score -= 20

        if h2_count > 0:
            score += 30

        if h3_count > 0:
            score += 20

        # Logical hierarchy
        if h1_count <= h2_count and h2_count >= h3_count:
            score += 10

        return max(min(score, 100.0), 0.0)

    def _find_missing_heading_levels(self, headers: Dict) -> List[str]:
        """Find missing heading levels in hierarchy."""
        missing = []

        has_h1 = bool(headers.get("h1"))
        has_h2 = bool(headers.get("h2"))
        has_h3 = bool(headers.get("h3"))

        if not has_h1:
            missing.append("h1")
        if has_h3 and not has_h2:
            missing.append("h2")

        return missing

    def _analyze_seo(self, parsed_data: Dict) -> Dict:
        """Analyze SEO quality of the page."""
        seo = {
            "title_length": 0,
            "meta_description_length": 0,
            "h1_count": 0,
            "issues": [],
            "score": 0.0,
        }

        title = parsed_data.get("title", "")
        meta_desc = parsed_data.get("meta_description", "")
        headers = parsed_data.get("headers", {})

        seo["title_length"] = len(title) if title else 0
        seo["meta_description_length"] = len(meta_desc) if meta_desc else 0
        seo["h1_count"] = len(headers.get("h1", []))

        # SEO issues
        if not title:
            seo["issues"].append("Missing title tag")
        elif len(title) < 30:
            seo["issues"].append("Title too short")
        elif len(title) > 60:
            seo["issues"].append("Title too long")

        if not meta_desc:
            seo["issues"].append("Missing meta description")
        elif len(meta_desc) > 160:
            seo["issues"].append("Meta description too long")

        if seo["h1_count"] == 0:
            seo["issues"].append("No H1 tag found")
        elif seo["h1_count"] > 1:
            seo["issues"].append("Multiple H1 tags found")

        # Calculate SEO score
        score = 100.0
        score -= len(seo["issues"]) * 15  # Deduct for each issue
        seo["score"] = max(score, 0.0)

        return seo

    def _extract_schema_markup(self, head_html: str) -> List[Dict]:
        """Extract schema.org structured data."""
        schemas = []

        # Find JSON-LD scripts
        json_ld_pattern = (
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        )
        matches = re.findall(json_ld_pattern, head_html, re.DOTALL | re.IGNORECASE)

        for match in matches:
            try:
                data = json.loads(match.strip())
                schemas.append(data)
            except:
                continue

        return schemas

    def _analyze_performance_hints(self, head_html: str) -> List[str]:
        """Analyze performance optimization hints from HTML head."""
        hints = []

        if "preload" in head_html:
            hints.append("Uses resource preloading")
        if "prefetch" in head_html:
            hints.append("Uses resource prefetching")
        if "preconnect" in head_html:
            hints.append("Uses DNS preconnection")
        if "dns-prefetch" in head_html:
            hints.append("Uses DNS prefetching")

        # Check for CDN usage
        cdn_indicators = ["cdn", "cloudflare", "fastly", "cloudfront", "jsdelivr"]
        if any(indicator in head_html.lower() for indicator in cdn_indicators):
            hints.append("Uses CDN")

        return hints
