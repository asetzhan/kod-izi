import { FEATURE_CODES, type FeatureScores, type LevelRule, type TaskLevel } from "./types";

/** Level from the rule for the given scores (spec 5.2); mirrors backend/app/services/levels.py. */
export function levelFor(rule: LevelRule, scores: FeatureScores): TaskLevel | undefined {
  const total = FEATURE_CODES.reduce((sum, code) => sum + scores[code], 0);
  return rule.sum_to_level.find((r) => r.min <= total && total <= r.max)?.level;
}
