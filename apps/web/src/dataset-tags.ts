import type { DataStage } from "./types";

export const dataStageOptions: {
  value: DataStage | "";
  label: string;
  description: string;
}[] = [
  {
    value: "",
    label: "None",
    description: "No lifecycle stage assigned.",
  },
  {
    value: "raw",
    label: "Raw",
    description: "Newly collected, without validation.",
  },
  {
    value: "raw_validated",
    label: "Raw validated",
    description: "Raw data that passed initial validation.",
  },
  {
    value: "prelabeled",
    label: "Prelabeled",
    description: "Labels were generated automatically.",
  },
  {
    value: "human_labeled",
    label: "Human labeled",
    description: "Labels were created or reviewed by people.",
  },
  {
    value: "verified",
    label: "Verified",
    description: "Quality checks are complete.",
  },
  {
    value: "training_ready",
    label: "Training ready",
    description: "Approved for model training.",
  },
  {
    value: "rejected",
    label: "Rejected",
    description: "Not approved for downstream use.",
  },
];

export function normalizeDatasetTag(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/-{2,}/g, "-");
}

export function isValidDatasetTag(value: string): boolean {
  return /^[a-z0-9][a-z0-9._-]{0,31}$/.test(value);
}
