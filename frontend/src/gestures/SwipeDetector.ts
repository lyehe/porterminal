/**
 * Swipe Detector - Detects swipe gestures for arrow key navigation
 * Single Responsibility: Swipe direction detection
 */

import type { SwipeResult } from '@/types';

/** Swipe detection configuration */
export interface SwipeConfig {
    /** Minimum swipe distance in pixels */
    minDistance: number;
    /** Maximum swipe time in ms */
    maxTime: number;
    /** Direction ratio (how much more dominant axis must be) */
    directionRatio: number;
}

export interface SwipeDetector {
    /** Detect swipe from start to end point, returns result with direction */
    detect(
        startX: number,
        startY: number,
        endX: number,
        endY: number,
        duration: number
    ): SwipeResult | null;
}

const DEFAULT_CONFIG: SwipeConfig = {
    minDistance: 25,
    maxTime: 300,
    directionRatio: 1.2,
};

/**
 * Create a swipe detector instance
 */
export function createSwipeDetector(config: Partial<SwipeConfig> = {}): SwipeDetector {
    const { minDistance, maxTime, directionRatio } = { ...DEFAULT_CONFIG, ...config };

    return {
        detect(
            startX: number,
            startY: number,
            endX: number,
            endY: number,
            duration: number
        ): SwipeResult | null {
            // Check time limit
            if (duration > maxTime) return null;

            const dx = endX - startX;
            const dy = endY - startY;
            const absDx = Math.abs(dx);
            const absDy = Math.abs(dy);

            // Check minimum distance
            const distance = Math.hypot(dx, dy);
            if (distance < minDistance) return null;

            // Only detect horizontal swipes (map to up/down arrows)
            // Left swipe = up, Right swipe = down
            if (absDx > absDy * directionRatio) {
                return { direction: dx > 0 ? 'down' : 'up' };
            }

            // Vertical swipes not detected (allows normal scrolling)
            return null;
        },
    };
}
