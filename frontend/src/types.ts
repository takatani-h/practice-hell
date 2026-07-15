export type Choice = { id: string; label: string };

export type Exercise = {
  join_code: string;
  title: string;
  answer_type: "number" | "single_choice";
  choices?: Choice[];
  mastery: {
    window_size: number;
    required_accuracy_percent: number;
  };
};
export type Question = {
  id: number;
  question_text: string;
  answer_type: "number" | "single_choice";
  choices?: Choice[];
};

export type Progress = {
  total_answers: number;
  recent_answers: number;
  recent_correct: number;
  recent_accuracy_percent: number;
  window_size: number;
  required_accuracy_percent: number;
  achieved: boolean;
};

export type Feedback = {
  correct: boolean;
  correct_answer: string;
  correct_answer_label: string;
  progress: Progress;
};
