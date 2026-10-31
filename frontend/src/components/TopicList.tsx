import { useTranslation } from "react-i18next";

import type { Topic } from "../api/types";

/** Topics with their Stepik lessons (ФТ-12: links only) and knowledge components. */
export function TopicList({ topics }: { topics: Topic[] }) {
  const { t } = useTranslation();
  return (
    <ol className="topics">
      {topics.map((topic) => (
        <li key={topic.id}>
          <strong>
            {topic.code} {topic.title}
          </strong>
          <ul>
            {topic.lessons.map((lesson) => (
              <li key={lesson.id}>
                <a href={lesson.url} target="_blank" rel="noopener noreferrer">
                  {lesson.title}
                </a>{" "}
                <small>({t("course.stepikLesson")})</small>
              </li>
            ))}
          </ul>
          {topic.knowledge_components.length > 0 && (
            <p className="muted">
              {t("course.knowledgeComponents")}:{" "}
              {topic.knowledge_components.map((kc) => kc.name).join("; ")}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
