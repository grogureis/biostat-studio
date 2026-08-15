import type { StudyBrief } from "./types";

const briefWithServerDefaults: StudyBrief = {
  title: "30-day outcome",
  question: "Does treatment reduce 30-day events?",
  hypothesis: "Treatment is associated with fewer events.",
  design: "cohort",
  outcome_variables: ["event_30_day"],
};

void briefWithServerDefaults;
