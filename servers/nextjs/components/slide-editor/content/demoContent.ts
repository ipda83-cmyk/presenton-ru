// Demo / placeholder content that the editor puts INTO slides (inserted
// charts, tables, infographics, "New item" rows, render fallbacks).
//
// This text belongs to the presentation, not to the UI, so it follows the
// PRESENTATION language rather than the interface locale. The editor page
// registers that language with setContentLocale(); pages without a
// presentation (template preview) register the UI locale instead.
//
// Only Russian has a dictionary for now; any other content language keeps
// the original English text.

export type ContentLocale = "ru" | "en";

let currentLocale: ContentLocale | null = null;

export function setContentLocale(locale: ContentLocale | null): void {
  currentLocale = locale;
}

export function getContentLocale(): ContentLocale {
  if (currentLocale) return currentLocale;
  if (typeof document !== "undefined") {
    return document.documentElement.lang === "ru" ? "ru" : "en";
  }
  return "en";
}

const CYRILLIC = /[А-Яа-яЁё]/g;
const LATIN = /[A-Za-z]/g;

// Keys that hold human-readable slide text. Slide JSON is mostly structural
// strings (types, ids, fonts, colors) that are Latin whatever the language,
// so only these are sampled when inferring the language.
const TEXT_SAMPLE_KEYS = new Set([
  "text",
  "title",
  "heading",
  "subtitle",
  "description",
  "label",
  "caption",
  "focus",
  "center_label",
]);

function collectText(
  value: unknown,
  out: string[],
  budget: { left: number },
  isText = false,
) {
  if (budget.left <= 0 || value == null) return;
  if (typeof value === "string") {
    if (isText && !/^[a-z0-9_.:#/-]*$/i.test(value)) {
      out.push(value);
      budget.left -= value.length;
    }
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectText(item, out, budget, isText);
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      collectText(item, out, budget, TEXT_SAMPLE_KEYS.has(key));
    }
  }
}

/**
 * Content language of a presentation. An explicit language wins; for an
 * empty or "Auto (...)" language the model picked the language from the
 * prompt, so it is inferred from the presentation's own text.
 */
export function resolvePresentationContentLocale(
  presentation:
    | { language?: string | null; title?: string | null; slides?: unknown }
    | null
    | undefined,
  fallback: ContentLocale,
): ContentLocale {
  if (!presentation) return fallback;
  const language = (presentation.language ?? "").trim();
  if (/russian|русск|^ru\b/i.test(language)) return "ru";
  if (language && !/^auto/i.test(language)) return "en";

  const parts: string[] = [];
  collectText(presentation.title ?? "", parts, { left: 400 }, true);
  collectText(presentation.slides, parts, { left: 4000 });
  const sample = parts.join(" ");
  const cyrillic = sample.match(CYRILLIC)?.length ?? 0;
  const latin = sample.match(LATIN)?.length ?? 0;
  if (cyrillic === 0 && latin === 0) return fallback;
  return cyrillic > latin ? "ru" : "en";
}

// "Item 3", "Stage 2", "Step 01", "Campaign B" ...
const NUMBERED_RU: Record<string, string> = {
  Item: "Элемент",
  Stage: "Этап",
  Step: "Шаг",
  Phase: "Фаза",
  Series: "Ряд",
  Option: "Вариант",
  Pillar: "Опора",
  Capability: "Направление",
  Stop: "Остановка",
  Level: "Уровень",
  Segment: "Сегмент",
  Column: "Столбец",
  Row: "Строка",
  Node: "Узел",
  Criterion: "Критерий",
  Component: "Компонент",
  Workstream: "Направление работ",
  Milestone: "Веха",
  Before: "До",
  After: "После",
  Campaign: "Кампания",
  Slide: "Слайд",
};

const RU: Record<string, string> = {
  // text blocks
  "Clarify the goal and audience": "Уточните цель и аудиторию",
  "Show the strongest supporting point": "Покажите самый сильный аргумент",
  "Close with the next action": "Завершите следующим шагом",
  "Add a clear slide title": "Добавьте понятный заголовок слайда",
  "Add a concise supporting subtitle": "Добавьте краткий поясняющий подзаголовок",
  '"Add a memorable quote or customer insight here."':
    "«Добавьте здесь запоминающуюся цитату или отзыв клиента.»",
  "Add body text here. Use this space for a short paragraph or supporting detail.":
    "Добавьте основной текст. Здесь уместен короткий абзац или поясняющая деталь.",
  // charts
  "Revenue Share by Segment": "Доля выручки по сегментам",
  Enterprise: "Крупный бизнес",
  "Mid-market": "Средний бизнес",
  "Small business": "Малый бизнес",
  Consumer: "Частные клиенты",
  "Revenue Share": "Доля выручки",
  "Qualified Leads by Channel": "Квалифицированные лиды по каналам",
  Email: "Эл. почта",
  Search: "Поиск",
  Social: "Соцсети",
  Referral: "Рекомендации",
  "Qualified Leads": "Квалифицированные лиды",
  "Support Tickets by Priority": "Обращения в поддержку по приоритету",
  Critical: "Критический",
  High: "Высокий",
  Medium: "Средний",
  Low: "Низкий",
  "Ticket Volume": "Число обращений",
  "Product Readiness Score": "Оценка готовности продукта",
  Design: "Дизайн",
  Reliability: "Надёжность",
  Speed: "Скорость",
  Security: "Безопасность",
  Usability: "Удобство",
  "Readiness Score": "Оценка готовности",
  "Campaign Conversion Results": "Конверсия рекламных кампаний",
  Conversions: "Конверсии",
  "Quarterly Revenue Trend": "Динамика выручки по кварталам",
  Revenue: "Выручка",
  Mon: "Пн",
  Tue: "Вт",
  Wed: "Ср",
  Thu: "Чт",
  Fri: "Пт",
  Sat: "Сб",
  Sun: "Вс",
  "Weekly Website Visits\nJun 10-16": "Посещения сайта за неделю\n10–16 июня",
  Visits: "Посещения",
  "Revenue Growth\n2021-2026": "Рост выручки\n2021–2026",
  "Monthly Active Users\n2021-2026": "Ежемесячные активные пользователи\n2021–2026",
  "Active Users": "Активные пользователи",
  Product: "Продукт",
  Services: "Услуги",
  Support: "Поддержка",
  Training: "Обучение",
  "Revenue Mix by Offering": "Структура выручки по направлениям",
  "Quarterly Revenue by Segment": "Выручка по сегментам за квартал",
  "New Business": "Новые клиенты",
  Expansion: "Расширение",
  Jan: "Янв",
  Feb: "Фев",
  Mar: "Мар",
  Apr: "Апр",
  May: "Май",
  Jun: "Июн",
  Jul: "Июл",
  Aug: "Авг",
  Sep: "Сен",
  Oct: "Окт",
  Nov: "Ноя",
  Dec: "Дек",
  Q1: "1 кв.",
  Q2: "2 кв.",
  Q3: "3 кв.",
  Q4: "4 кв.",
  // gantt
  "Research & Discovery": "Исследование и анализ",
  "Content Planning": "Планирование контента",
  "Strategy Development": "Разработка стратегии",
  "Design & Production": "Дизайн и производство",
  "Content Creation": "Создание контента",
  "Campaign Launch": "Запуск кампании",
  "Performance Tracking": "Отслеживание результатов",
  Optimization: "Оптимизация",
  "Final Review": "Итоговый обзор",
  // timeline / roadmap / process
  Discover: "Исследование",
  "Research the challenge and identify key needs.":
    "Изучите задачу и определите ключевые потребности.",
  Define: "Определение",
  "Set clear goals, priorities, and direction.":
    "Задайте чёткие цели, приоритеты и направление.",
  Plan: "Планирование",
  "Build the strategy, timeline, and action plan.":
    "Сформируйте стратегию, сроки и план действий.",
  Execute: "Реализация",
  "Put the plan into action and track progress.":
    "Воплотите план и отслеживайте прогресс.",
  Measure: "Измерение",
  "Review results against key performance indicators.":
    "Сравните результаты с ключевыми показателями.",
  Review: "Разбор итогов",
  "Capture lessons and decide the next direction.":
    "Зафиксируйте выводы и выберите дальнейшее направление.",
  "Defined the project vision, objectives, and strategic direction.":
    "Определены видение проекта, цели и стратегическое направление.",
  "Drive Growth": "Ускорить рост",
  "Expand customer reach, improve engagement, and increase revenue.":
    "Расширяйте охват клиентов, повышайте вовлечённость и выручку.",
  "Enter the Market": "Выйти на рынок",
  "Launch strategically and establish a strong market presence.":
    "Продуманно запуститесь и закрепитесь на рынке.",
  "Build the Solution": "Создать решение",
  "Develop products, services, and experiences.":
    "Разрабатывайте продукты, услуги и клиентский опыт.",
  "Understand Market": "Изучить рынок",
  "Identify customer needs, market trends, and competitive gaps.":
    "Выявите потребности клиентов, тренды рынка и свободные ниши.",
  "Define the Vision": "Сформулировать видение",
  "Set clear goals, priorities, and a long-term direction.":
    "Задайте чёткие цели, приоритеты и долгосрочное направление.",
  // supply chain
  SOURCING: "СНАБЖЕНИЕ",
  "Raw materials\nSupplier network": "Сырьё\nСеть поставщиков",
  PROCUREMENT: "ЗАКУПКИ",
  "Purchasing\nQuality & cost": "Закупки\nКачество и цена",
  PRODUCTION: "ПРОИЗВОДСТВО",
  "Manufacturing\nQuality control": "Изготовление\nКонтроль качества",
  DISTRIBUTION: "ДИСТРИБУЦИЯ",
  "Warehousing\nLogistics & delivery": "Склад\nЛогистика и доставка",
  "END MARKET": "КОНЕЧНЫЙ РЫНОК",
  "Retail / B2B\nCustomer delivery": "Розница / B2B\nДоставка клиентам",
  // step blocks
  Foundation: "Фундамент",
  "Establish core capabilities, clear processes, resources, and operating structures.":
    "Сформируйте базовые компетенции, понятные процессы, ресурсы и операционную структуру.",
  Optimize: "Оптимизация",
  "Streamline workflows, improve efficiency, reduce bottlenecks, and strengthen performance.":
    "Упростите процессы, повысьте эффективность, устраните узкие места и улучшите результаты.",
  Scale: "Масштабирование",
  "Expand capacity, customer reach, technology, and operational capabilities to support growth.":
    "Наращивайте мощности, охват клиентов, технологии и операционные возможности для роста.",
  Accelerate: "Ускорение",
  "Invest in innovation, new opportunities, partnerships, and high-impact growth initiatives.":
    "Инвестируйте в инновации, новые возможности, партнёрства и инициативы с высоким эффектом.",
  Lead: "Лидерство",
  "Build market leadership through continuous improvement and differentiation.":
    "Укрепляйте лидерство на рынке через постоянное улучшение и отличия от конкурентов.",
  // maturity model
  Initial: "Начальный",
  "Capabilities are continuously refined through automation, innovation, advanced analytics, and proactive performance management.":
    "Возможности постоянно совершенствуются за счёт автоматизации, инноваций, продвинутой аналитики и проактивного управления результатами.",
  Developing: "Развивающийся",
  "Performance is actively measured through KPIs and data, enabling teams to identify gaps and manage outcomes.":
    "Результаты активно измеряются через KPI и данные, что помогает командам находить пробелы и управлять итогами.",
  Defined: "Определённый",
  "Core processes are standardized, documented, and consistently applied, with clearer roles and governance.":
    "Ключевые процессы стандартизированы, задокументированы и применяются последовательно, роли и управление понятнее.",
  Managed: "Управляемый",
  "Basic processes and responsibilities are emerging, but execution varies across teams.":
    "Базовые процессы и зоны ответственности формируются, но исполнение различается между командами.",
  Optimized: "Оптимизированный",
  "Processes are largely informal and reactive, with limited standardization or clear ownership.":
    "Процессы в основном неформальные и реактивные, стандартизации и явной ответственности мало.",
  // pillars / hub
  Customer: "Клиенты",
  "Strengthen customer relationships, improve experience, and deliver greater value across key touchpoints.":
    "Укрепляйте отношения с клиентами, улучшайте опыт и создавайте больше ценности в ключевых точках контакта.",
  "Experience & Value": "Опыт и ценность",
  Growth: "Рост",
  "Expand market presence, develop new opportunities, and build sustainable revenue streams.":
    "Расширяйте присутствие на рынке, развивайте новые возможности и создавайте устойчивые источники выручки.",
  "Revenue & Market": "Выручка и рынок",
  Operations: "Операции",
  "Simplify processes, improve productivity, and build scalable operating capabilities.":
    "Упрощайте процессы, повышайте производительность и создавайте масштабируемые операционные возможности.",
  "Efficiency & Scale": "Эффективность и масштаб",
  Innovation: "Инновации",
  "Leverage technology, data, and innovation to create new solutions and differentiation.":
    "Используйте технологии, данные и инновации, чтобы создавать новые решения и отличаться от конкурентов.",
  "Digital & New Ideas": "Цифровизация и новые идеи",
  People: "Люди",
  "Develop capabilities, strengthen leadership, and create a culture of ownership and continuous improvement.":
    "Развивайте компетенции, укрепляйте лидерство и создавайте культуру ответственности и постоянного улучшения.",
  "Talent & Culture": "Таланты и культура",
  "Business\nTransformation": "Бизнес-\nтрансформация",
  "Business Transformation": "Бизнес-трансформация",
  "Growth & Transformation Framework": "Модель роста и трансформации",
  Strategy: "Стратегия",
  "Defines the organization's direction, priorities, objectives, and investment focus.":
    "Определяет направление организации, приоритеты, цели и фокус инвестиций.",
  "Builds the skills, leadership, accountability, and culture required to execute strategy.":
    "Развивает навыки, лидерство, ответственность и культуру, нужные для реализации стратегии.",
  "Focuses on customer needs, experience, engagement, and value creation.":
    "Сосредоточена на потребностях клиентов, их опыте, вовлечённости и создании ценности.",
  Process: "Процессы",
  "Improves workflows, standardization, efficiency, and governance.":
    "Улучшает рабочие процессы, стандартизацию, эффективность и управление.",
  Technology: "Технологии",
  "Enables digital transformation through systems, automation, integration, and data-driven capabilities.":
    "Обеспечивает цифровую трансформацию через системы, автоматизацию, интеграцию и работу с данными.",
  // risk matrix
  Identify: "Выявление",
  "Detect potential risks across operations, technology, finance, people, and external factors.":
    "Выявляйте потенциальные риски в операциях, технологиях, финансах, персонале и внешней среде.",
  Prioritize: "Приоритизация",
  "Rank risks by severity to focus attention and resources on the most critical areas.":
    "Ранжируйте риски по серьёзности, чтобы сосредоточить внимание и ресурсы на самом критичном.",
  Assess: "Оценка",
  "Evaluate likelihood, impact, and exposure to understand each risk.":
    "Оцените вероятность, последствия и уязвимость, чтобы понять каждый риск.",
  Respond: "Реагирование",
  "Define mitigation actions, controls, owners, and contingency plans for priority risks.":
    "Определите меры снижения, контроль, ответственных и запасные планы для приоритетных рисков.",
  RISK: "РИСК",
  // chevron / radial cycle
  "Understand the business, market, and key challenges.":
    "Разберитесь в бизнесе, рынке и ключевых вызовах.",
  Analyze: "Анализ",
  "Evaluate data, trends, competitors, and opportunities.":
    "Оцените данные, тренды, конкурентов и возможности.",
  "Prioritize strategic issues and define objectives.":
    "Расставьте приоритеты стратегических задач и определите цели.",
  "Develop solutions, initiatives, and strategic priorities.":
    "Разработайте решения, инициативы и стратегические приоритеты.",
  Implement: "Внедрение",
  "Build the roadmap, actions, owners, and next steps.":
    "Составьте дорожную карту, действия, ответственных и следующие шаги.",
  "Review data, identify patterns, and evaluate opportunities.":
    "Изучите данные, найдите закономерности и оцените возможности.",
  "Define priorities, develop the approach, and establish clear actions.":
    "Определите приоритеты, выработайте подход и задайте конкретные действия.",
  "Implement the recommended actions and track progress.":
    "Выполните рекомендованные действия и отслеживайте прогресс.",
  "Measure performance and improve the plan.": "Измеряйте результаты и улучшайте план.",
  Finalize: "Завершение",
  "Capture outcomes, decisions, and next steps.":
    "Зафиксируйте результаты, решения и следующие шаги.",
  // funnels
  Awareness: "Осведомлённость",
  Interest: "Интерес",
  "Users showing engagement with the offering.": "Пользователи проявляют интерес к предложению.",
  Consideration: "Рассмотрение",
  "Prospects evaluating the solution.": "Потенциальные клиенты оценивают решение.",
  Intent: "Намерение",
  "Users showing strong purchase interest.": "Пользователи готовы к покупке.",
  "The full audience entering the funnel.": "Вся аудитория на входе в воронку.",
  "People engaging with the offering.": "Люди, взаимодействующие с предложением.",
  Conversion: "Конверсия",
  "People completing the target action.": "Люди, совершившие целевое действие.",
  // pyramid
  "Establish strong processes, capabilities, and resources.":
    "Выстройте сильные процессы, компетенции и ресурсы.",
  Efficiency: "Эффективность",
  "Streamline operations, reduce gaps, and optimize costs.":
    "Упростите операции, закройте пробелы и оптимизируйте затраты.",
  "Enter new markets, strengthen offerings, and increase reach.":
    "Выходите на новые рынки, усиливайте предложение и расширяйте охват.",
  "Develop new ideas, solutions, and competitive advantages.":
    "Развивайте новые идеи, решения и конкурентные преимущества.",
  Leadership: "Лидерство",
  "Build long-term resilience, market leadership, and value creation.":
    "Обеспечьте долгосрочную устойчивость, лидерство на рынке и создание ценности.",
  // customer journey
  "Customer discovers the brand through marketing and referrals.":
    "Клиент узнаёт о бренде из рекламы и рекомендаций.",
  "Customer explores options, compares alternatives.":
    "Клиент изучает варианты и сравнивает альтернативы.",
  Purchase: "Покупка",
  "Customer makes a decision and completes the transaction.":
    "Клиент принимает решение и совершает покупку.",
  Experience: "Опыт",
  "Customer uses the product or service and interacts with support.":
    "Клиент пользуется продуктом или услугой и общается с поддержкой.",
  // before / after
  "Manual Processes": "Ручные процессы",
  "Time-consuming workflows.": "Трудоёмкие процессы.",
  "Limited Visibility": "Мало прозрачности",
  "Data is difficult to access.": "Данные трудно получить.",
  "Fragmented Workflows": "Разрозненные процессы",
  "Teams work in silos.": "Команды работают обособленно.",
  "Automated Processes": "Автоматизированные процессы",
  "Faster, streamlined operations.": "Быстрые и слаженные операции.",
  "Faster Decisions": "Быстрые решения",
  "Quicker, data-driven actions.": "Оперативные действия на основе данных.",
  "Connected Workflows": "Связанные процессы",
  "Better team collaboration.": "Лучшее взаимодействие команд.",
  Before: "До",
  After: "После",
  // impact / effort
  Impact: "Эффект",
  Effort: "Усилия",
  "Quick Wins": "Быстрые победы",
  "High-impact initiatives that require relatively low effort, making them ideal for immediate execution and fast results.":
    "Инициативы с высоким эффектом и относительно небольшими усилиями — идеальны для немедленного запуска и быстрых результатов.",
  "Strategic Priorities": "Стратегические приоритеты",
  "High-impact initiatives that require significant investment, planning, and resources but can drive long-term business value.":
    "Инициативы с высоким эффектом, требующие серьёзных вложений, планирования и ресурсов, но создающие долгосрочную ценность.",
  Deprioritize: "Отложить",
  "Low-impact initiatives requiring substantial effort or resources, making them less suitable for immediate focus.":
    "Инициативы с низким эффектом, требующие больших усилий или ресурсов, — не для первоочередного внимания.",
  "Fill-ins": "Дополнительные задачи",
  "Low-impact initiatives that are easy to implement and can be addressed when resources are available.":
    "Инициативы с низким эффектом, которые легко реализовать при наличии свободных ресурсов.",
  "High-impact initiatives requiring relatively low effort.":
    "Высокий эффект при относительно небольших усилиях.",
  "High-impact initiatives requiring significant investment.":
    "Высокий эффект, но нужны серьёзные вложения.",
  "Low-impact initiatives requiring substantial effort.": "Низкий эффект при больших усилиях.",
  "Low-impact initiatives that are easy to implement.": "Низкий эффект, но легко реализовать.",
  // comparison matrix
  "Market Access": "Доступ к рынку",
  "Investment Required": "Нужные инвестиции",
  "Speed to Market": "Скорость выхода на рынок",
  Control: "Контроль",
  Scalability: "Масштабируемость",
  "Organic Growth": "Органический рост",
  Moderate: "Умеренно",
  Slow: "Медленно",
  "Product Innovation": "Продуктовые инновации",
  Fast: "Быстро",
  "Strategic Partnership": "Стратегическое партнёрство",
  Acquisition: "Поглощение",
  "Market Expansion": "Расширение рынка",
  Criteria: "Критерии",
  Criterion: "Критерий",
  // org chart (sample people)
  "Aarav Sharma": "Алексей Смирнов",
  "Chief Executive Officer": "Генеральный директор",
  "Nisha Kapoor": "Наталья Кузнецова",
  "Chief Operating Officer": "Операционный директор",
  "Rohan Mehta": "Роман Морозов",
  "Chief Financial Officer": "Финансовый директор",
  "Priya Malhotra": "Полина Максимова",
  "Chief Marketing Officer": "Директор по маркетингу",
  "Rohan Thapa": "Руслан Тихонов",
  "Operations Manager": "Руководитель операций",
  "Vikram Joshi": "Виктор Жуков",
  "Product Manager": "Продакт-менеджер",
  "Rahul Nair": "Родион Никитин",
  "Finance Manager": "Финансовый менеджер",
  "Sneha Gurung": "Светлана Гусева",
  "Operations Executive": "Специалист по операциям",
  "Amit Shrestha": "Андрей Шестаков",
  "Process Analyst": "Аналитик процессов",
  "Aditya Rao": "Артём Романов",
  "Finance Executive": "Финансовый специалист",
  "Dev Sharma": "Денис Шарапов",
  Accountant: "Бухгалтер",
  Role: "Роль",
  // decision tree
  "Market Expansion Decision": "Решение о выходе на новый рынок",
  "Market Demand": "Спрос на рынке",
  "Competitive Position": "Позиция среди конкурентов",
  "Investment Feasibility": "Реалистичность инвестиций",
  "Operational Readiness": "Операционная готовность",
  "Growth Potential": "Потенциал роста",
  "Competition Level": "Уровень конкуренции",
  "Market Saturation": "Насыщенность рынка",
  "Limited capacity": "Ограниченные мощности",
  "Funding required": "Нужно финансирование",
  "Fully ready": "Полностью готовы",
  "Partially ready": "Частично готовы",
  // image blocks
  "Image with heading and supporting text": "Изображение с заголовком и текстом",
  "Add a heading": "Добавьте заголовок",
  "Add supporting text that explains why this visual matters.":
    "Добавьте текст, объясняющий, почему это изображение важно.",
  "Two-by-two image grid": "Сетка изображений 2×2",
  // table
  Metric: "Показатель",
  Current: "Сейчас",
  Target: "Цель",
  Activation: "Активация",
  Retention: "Удержание",
  // editor defaults and render fallbacks
  "New item": "Новый пункт",
  "Add a description.": "Добавьте описание.",
  "Focus area": "Фокус",
  Activity: "Действие",
  Quadrant: "Квадрант",
  "New task": "Новая задача",
  Task: "Задача",
  "Core idea": "Ключевая идея",
  Destination: "Цель",
  Sourcing: "Снабжение",
  Phase: "Фаза",
  Step: "Шаг",
  Stage: "Этап",
  Workstream: "Направление работ",
  Milestone: "Веха",
  Data: "Данные",
  Text: "Текст",
  "List item": "Пункт списка",
  Series: "Ряд",
};

const NUMBERED_PATTERN = new RegExp(
  `^(${Object.keys(NUMBERED_RU).join("|")}) (\\d+|[A-Z])$`,
);

function translateRu(text: string): string | null {
  const exact = RU[text];
  if (exact !== undefined) return exact;
  const numbered = NUMBERED_PATTERN.exec(text);
  if (numbered) return `${NUMBERED_RU[numbered[1]]} ${numbered[2]}`;
  if (text.includes("\n")) {
    const lines = text.split("\n");
    const translated = lines.map((line) => translateRu(line));
    if (translated.some((line) => line !== null)) {
      return translated.map((line, index) => line ?? lines[index]).join("\n");
    }
  }
  return null;
}

/** Translate one demo/placeholder string into the current content language. */
export function demo(text: string, locale: ContentLocale = getContentLocale()): string {
  if (locale !== "ru") return text;
  return translateRu(text) ?? text;
}

/** True when `value` is the default `english` text in any content language. */
export function isDemoDefault(value: unknown, english: string): boolean {
  return value === english || value === translateRu(english);
}

// Object keys whose string values are slide content. Everything else (ids,
// types, colors, fonts, icon/image urls, layout keys) is left untouched.
const CONTENT_KEYS = new Set([
  "text",
  "title",
  "heading",
  "description",
  "label",
  "name",
  "seriesName",
  "categories",
  "values",
  "criteria",
  "focus",
  "subtitle",
  "caption",
  "center_label",
  "x_axis_label",
  "y_axis_label",
  "x_axis_title",
  "y_axis_title",
  "low_label",
  "high_label",
  "before_label",
  "after_label",
]);

const SKIP_KEYS = new Set(["icon", "font", "fill", "stroke", "border", "shadow", "image", "src", "url"]);

function localizeNode(value: unknown, locale: ContentLocale, contentKey: boolean): unknown {
  if (typeof value === "string") {
    return contentKey ? demo(value, locale) : value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => localizeNode(item, locale, contentKey));
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(record)) {
      out[key] = SKIP_KEYS.has(key) ? item : localizeNode(item, locale, CONTENT_KEYS.has(key));
    }
    // Inserted text boxes carry length bounds derived from the English
    // sample; keep them valid for the translated text.
    if (Array.isArray(out.runs) && typeof out.max_length === "number") {
      const length = (out.runs as Array<{ text?: unknown }>)
        .map((run) => (typeof run?.text === "string" ? run.text.trim().length : 0))
        .reduce((sum, part) => sum + part, 0);
      if (length > out.max_length) {
        out.max_length = length;
        out.min_length = Math.ceil(length / 2);
      }
    }
    return out;
  }
  return value;
}

/**
 * Translate the demo content of freshly created slide elements (or any
 * element-like tree) into the current content language.
 */
export function localizeDemoContent<T>(value: T, locale: ContentLocale = getContentLocale()): T {
  if (locale !== "ru") return value;
  return localizeNode(value, locale, false) as T;
}
