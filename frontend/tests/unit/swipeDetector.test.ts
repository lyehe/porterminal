import { describe, expect, it } from 'vitest';

import { createSwipeDetector } from '@/gestures/SwipeDetector';


describe('swipe detector', () => {
    const detector = createSwipeDetector();

    it('maps horizontal history gestures to terminal arrow directions', () => {
        expect(detector.detect(100, 20, 20, 25, 150)).toEqual({ direction: 'up' });
        expect(detector.detect(20, 20, 100, 25, 150)).toEqual({ direction: 'down' });
    });

    it('ignores slow, short, and vertical gestures', () => {
        expect(detector.detect(0, 0, 100, 0, 500)).toBeNull();
        expect(detector.detect(0, 0, 10, 0, 100)).toBeNull();
        expect(detector.detect(0, 0, 5, 100, 100)).toBeNull();
    });
});
