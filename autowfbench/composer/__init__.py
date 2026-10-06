"""Black-box workflow Composer.

The Composer owns candidate generation and search. It receives only public
challenge data and allowlisted numeric benchmark observations.
"""

from autowfbench.composer.models import NumericObservation, validate_candidate

__all__ = ["NumericObservation", "validate_candidate"]
