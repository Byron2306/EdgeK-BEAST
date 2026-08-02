# Phase 9.1.3 implementation notes

## Root cause

The background animation canvases were functioning, but most shell surfaces and dynamic page panels used 0.91–0.99 alpha backgrounds. Because the rain and grid are beneath the application shell, those panels physically occluded the animation.

## Fix

The final cascade introduces a glass contract using 0.38–0.70 alpha backgrounds and backdrop filtering. Dense reading surfaces remain darker. Controls retain their Phase 9.1.2 contrast treatment.

The previous header used absolutely positioned blocks and limited the wordmark to 47px. Phase 9.1.3 replaces that geometry with a two-row CSS grid and a 92px desktop wordmark, avoiding another overlap regression.
