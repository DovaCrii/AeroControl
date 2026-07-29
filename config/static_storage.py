"""Production static-file storage for AeroControl.

Third-party assets in ``static/vendor`` are served with Subresource Integrity
(SRI) hashes.  Django's default manifest post-processor rewrites relative
URLs, including source-map comments, inside CSS and JavaScript files.  That
changes the bytes delivered to the browser after the SRI hash was calculated,
so browsers correctly reject the asset.

The manifest still supplies content-hashed filenames for cache invalidation;
we simply leave vendored file bytes untouched.  The original, unhashed copies
remain available for relative images and source maps.
"""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class AeroControlStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Keep static asset contents stable so their SRI hashes remain valid."""

    patterns = ()
