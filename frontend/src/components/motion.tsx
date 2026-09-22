"use client";

import { useEffect } from "react";

const motionTargets = "[data-reveal], [data-probability-bar], [data-probability-split], [data-interval-reveal]";

export function MotionEnhancer() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window) || !("animate" in Element.prototype)) {
      return;
    }

    const observed = new WeakSet<Element>();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const target = entry.target as HTMLElement;
        if (target.hasAttribute("data-probability-bar")) {
          target.querySelector<HTMLElement>(".probability__fill")?.animate(
            [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }],
            { duration: 700, easing: "cubic-bezier(.2,.7,.2,1)", fill: "both" },
          );
        } else if (target.hasAttribute("data-interval-reveal")) {
          target.animate(
            [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }],
            { duration: 620, easing: "cubic-bezier(.2,.7,.2,1)", fill: "both" },
          );
        } else if (target.hasAttribute("data-probability-split")) {
          target.animate(
            [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }],
            { duration: 700, easing: "cubic-bezier(.2,.7,.2,1)", fill: "both" },
          );
        } else {
          target.animate(
            [{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "translateY(0)" }],
            { duration: 520, easing: "cubic-bezier(.2,.7,.2,1)", fill: "both" },
          );
        }
        observer.unobserve(target);
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });

    function observe(target: HTMLElement) {
      if (observed.has(target)) return;
      observed.add(target);
      observer.observe(target);
    }

    document.querySelectorAll<HTMLElement>(motionTargets).forEach(observe);
    const mutations = new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (!(node instanceof HTMLElement)) continue;
          if (node.matches(motionTargets)) observe(node);
          node.querySelectorAll<HTMLElement>(motionTargets).forEach(observe);
        }
      }
    });
    mutations.observe(document.body, { childList: true, subtree: true });

    return () => {
      mutations.disconnect();
      observer.disconnect();
    };
  }, []);

  return null;
}
