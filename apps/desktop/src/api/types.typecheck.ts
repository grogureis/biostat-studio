import type { StudyBrief } from "./types";

const briefWithServerDefaults: StudyBrief = {
  title: "30-day outcome",
  question: "Does treatment reduce 30-day events?",
  hypothesis: "Treatment is associated with fewer events.",
  design: "cohort",
  outcome_variables: ["event_30_day"],
};

const repeatedBrief: StudyBrief = {
  title: "Repeated outcome",
  question: "Does the outcome differ between conditions?",
  hypothesis: "The paired conditions differ.",
  design: "repeated",
  outcome_variables: ["score"],
  exposure_variables: ["condition"],
  pair_id_variable: "participant_id",
};

void briefWithServerDefaults;
void repeatedBrief;
