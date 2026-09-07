import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export type LegalPageKind = "privacy" | "terms" | "cookies" | "refund" | "legal";

const LAST_UPDATED = "7 September 2026";

const OPERATOR_NOTICE = (
  <div className="border border-band-moderate/40 bg-surface-2 px-4 py-3 text-sm leading-relaxed">
    <strong>Operator details require completion before public commercial launch.</strong> SignalDesk is
    currently a project name. The final legal entity name, registered/business address, and a dedicated
    legal/privacy contact must be published here before the site is used to collect customer data or
    accept payment. This page intentionally does not invent those details.
  </div>
);

function LegalShell({ title, kicker, children }: { title: string; kicker: string; children: ReactNode }) {
  return (
    <article className="mx-auto max-w-4xl px-4 py-12 md:px-6 md:py-16">
      <header className="mb-10 border-b border-line pb-8">
        <p className="label-caps">{kicker}</p>
        <h1 className="mt-3 font-display text-4xl font-semibold tracking-[-0.015em] md:text-5xl">{title}</h1>
        <p className="mt-3 text-xs text-muted">Last updated: {LAST_UPDATED}</p>
      </header>
      <div className="space-y-10 text-sm leading-7 text-muted">{children}</div>
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-2xl font-semibold text-foreground">{title}</h2>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function Links() {
  return (
    <p>
      Related policies: <Link className="text-cobalt underline underline-offset-2" to="/privacy">Privacy Policy</Link>,{" "}
      <Link className="text-cobalt underline underline-offset-2" to="/terms">Terms &amp; Conditions</Link>,{" "}
      <Link className="text-cobalt underline underline-offset-2" to="/cookies">Cookie Policy</Link>, and{" "}
      <Link className="text-cobalt underline underline-offset-2" to="/refunds">Refund Policy</Link>.
    </p>
  );
}

function PrivacyPolicy() {
  return (
    <LegalShell title="Privacy Policy" kicker="Legal · Privacy">
      {OPERATOR_NOTICE}
      <Section title="1. Scope">
        <p>This policy explains how SignalDesk handles information when you use the public website and research application. The current application has no user accounts, advertising system, analytics tracker, marketing form, or payment flow.</p>
      </Section>
      <Section title="2. Information the current site processes">
        <ul className="list-disc space-y-2 pl-5">
          <li><strong className="text-foreground">Stock searches:</strong> search text is used in the browser to filter the stock catalogue. It is not an account record.</li>
          <li><strong className="text-foreground">Research questions:</strong> questions submitted to the stock research assistant are sent to the configured LLM provider so that the service can answer them. Do not submit passwords, financial-account credentials, government identifiers, health information, or other sensitive personal information.</li>
          <li><strong className="text-foreground">Technical request data:</strong> the backend generates a short request ID and records request method, path, status, and duration for operations and troubleshooting. Application logging does not intentionally record request bodies, credentials, API keys, or authorization headers.</li>
          <li><strong className="text-foreground">Theme preference:</strong> the browser stores the light/dark preference in local storage. This is a functional preference, not an advertising tracker.</li>
        </ul>
      </Section>
      <Section title="3. Data minimisation">
        <p>SignalDesk is designed to collect only information needed to operate the requested research function, protect the service, diagnose failures, and maintain security. There is currently no account profile, contact database, marketing list, behavioural advertising profile, or sale of user data.</p>
      </Section>
      <Section title="4. AI processing">
        <p>The research assistant is a single-shot feature. The backend supplies the model with an explicitly allow-listed set of SignalDesk research facts and the submitted question. The model is not given arbitrary database access and the application does not maintain chat history for this feature. Processing is performed by the configured LLM provider. Provider retention and processing terms may therefore apply to the submitted question and the research context sent to that provider.</p>
      </Section>
      <Section title="5. Cookies, analytics and third parties">
        <p>The current frontend does not set cookies and does not load browser analytics, advertising pixels, social widgets, video embeds, remote fonts, or third-party chart embeds. Fonts are bundled with the application. Market-data, news, sentiment and LLM providers are backend integrations, not browser embeds.</p>
        <p>If non-essential analytics, advertising, or third-party embeds are introduced later, the privacy and cookie controls will be updated before those technologies are activated where applicable law requires consent.</p>
      </Section>
      <Section title="6. Your rights and requests">
        <p>Applicable Indian data-protection law may provide rights concerning access, correction, erasure, grievance redressal, consent withdrawal, and related matters. The Digital Personal Data Protection Act, 2023 and the Digital Personal Data Protection Rules, 2025 are the principal current framework in India, subject to their respective commencement provisions.</p>
        <p>A dedicated privacy contact must be published before this site is used as a public customer service. Until that contact is added, do not submit personal or sensitive information through the application.</p>
      </Section>
      <Section title="7. Security and retention">
        <p>SignalDesk uses request IDs, structured operational logging, provider isolation, and explicit error handling. Retention periods for infrastructure logs depend on the production hosting configuration and will be documented before deployment. Data is not retained merely for analytics when no analytics system exists.</p>
      </Section>
      <Section title="8. Changes">
        <p>This policy may be updated when the product, data flows, providers, or applicable law changes. The effective date shown at the top will be updated with material changes.</p>
      </Section>
      <Links />
    </LegalShell>
  );
}

function Terms() {
  return (
    <LegalShell title="Terms & Conditions" kicker="Legal · Terms">
      {OPERATOR_NOTICE}
      <Section title="1. Nature of the service">
        <p>SignalDesk is a financial research and information interface for Indian equities. It presents provider-sourced market data, financial ratios, relative valuation, technical indicators, news sentiment, and derived research scores. The service is informational and analytical only.</p>
        <p>SignalDesk does not currently execute trades, hold customer funds, provide personalised investment advice, manage portfolios, or operate a brokerage account.</p>
      </Section>
      <Section title="2. No investment advice or guarantee">
        <p>Nothing on the site is a recommendation to buy, sell, hold, subscribe to, or otherwise transact in a security. Scores and technical verdicts describe the methodology's computed evidence and are not promises of future performance. Past performance, where displayed, does not guarantee future results.</p>
        <p>Financial markets involve substantial risk. You are responsible for your own investment decisions and for obtaining professional advice appropriate to your circumstances.</p>
      </Section>
      <Section title="3. Data and methodology">
        <p>Data is obtained from third-party sources and may be delayed, incomplete, unavailable, revised, or wrong. SignalDesk's methodology page describes how derived scores are calculated. Missing data is intentionally shown as missing rather than fabricated.</p>
      </Section>
      <Section title="4. Research assistant">
        <p>The research assistant is grounded to a defined evidence set and may use a language model to produce a concise explanation. Model output can contain errors. It is not a substitute for checking the underlying data or methodology. Do not submit confidential or sensitive information.</p>
      </Section>
      <Section title="5. Acceptable use">
        <ul className="list-disc space-y-2 pl-5">
          <li>Do not attempt to disrupt, overload, reverse engineer, or bypass security controls.</li>
          <li>Do not use the service to submit unlawful, malicious, fraudulent, or abusive content.</li>
          <li>Do not treat automated output as a guaranteed financial outcome.</li>
          <li>Do not represent SignalDesk content as your own research where doing so would infringe rights.</li>
        </ul>
      </Section>
      <Section title="6. Intellectual property and third-party material">
        <p>The SignalDesk software, original interface, methodology text, and original content are protected by applicable intellectual-property law unless stated otherwise. Third-party market data, news, trademarks, and other material remain subject to their respective owners' rights and terms.</p>
      </Section>
      <Section title="7. Availability and changes">
        <p>The service may be unavailable during maintenance, provider outages, data-refresh failures, or other technical events. Features and data sources may change as the product evolves.</p>
      </Section>
      <Section title="8. Liability">
        <p>To the extent permitted by applicable law, SignalDesk is not responsible for investment losses, trading decisions, data-source errors, outages, or indirect losses arising from reliance on the service. Nothing in these terms excludes liability that cannot lawfully be excluded.</p>
      </Section>
      <Section title="9. Regulatory position">
        <p>SignalDesk is not currently presented as a SEBI-registered research analyst or investment adviser. If the product later offers paid research services, personalised advice, model portfolios, buy/sell/hold recommendations, or other regulated services, the regulatory position must be reassessed before launch.</p>
      </Section>
      <Section title="10. Applicable law">
        <p>These terms are intended for a service operated in India and are subject to applicable Indian law, while preserving any mandatory rights that apply to a user under the law that governs their transaction.</p>
      </Section>
      <Links />
    </LegalShell>
  );
}

function Cookies() {
  return (
    <LegalShell title="Cookie Policy" kicker="Legal · Cookies">
      <Section title="1. Current cookie status">
        <p>SignalDesk currently does <strong className="text-foreground">not use cookies</strong> for analytics, advertising, behavioural profiling, or authentication. No cookie-consent banner is therefore required for the current implementation merely because the site is visited.</p>
      </Section>
      <Section title="2. Local storage">
        <p>The site stores one functional preference, the selected light/dark theme, in browser local storage. It is not a cookie and is not used to track browsing activity.</p>
      </Section>
      <Section title="3. Analytics and future tracking">
        <p>There is no browser analytics SDK in the current application. If an analytics, advertising, social, reCAPTCHA, embedded-video, or other tracking technology that creates non-essential identifiers is added, it must be reviewed for applicable consent and disclosure requirements before activation.</p>
      </Section>
      <Section title="4. How consent will work if tracking is introduced">
        <p>Where consent is legally required, non-essential technologies will remain disabled until the user makes an affirmative choice. Refusing non-essential tracking will not disable core research functionality. A settings control will be provided to withdraw or change the choice.</p>
      </Section>
      <Links />
    </LegalShell>
  );
}

function Refunds() {
  return (
    <LegalShell title="Refund Policy" kicker="Legal · Refunds">
      {OPERATOR_NOTICE}
      <Section title="1. Current status">
        <p>SignalDesk currently does not sell subscriptions, paid research reports, memberships, data packages, consultations, or other paid digital services through this website. There is therefore currently no purchase price for which a refund can be claimed.</p>
      </Section>
      <Section title="2. Future paid services">
        <p>If paid services are introduced, the applicable price, billing cycle, cancellation terms, refund eligibility, statutory consumer rights, and refund process will be shown before payment is taken. Those terms will not be replaced by this placeholder policy.</p>
      </Section>
      <Section title="3. No payment collection today">
        <p>The current frontend contains no payment gateway, checkout form, subscription management, or stored payment method. Do not send card numbers, bank credentials, UPI PINs, or other payment credentials through SignalDesk forms.</p>
      </Section>
      <Links />
    </LegalShell>
  );
}

function LegalDetails() {
  return (
    <LegalShell title="Legal & Business Details" kicker="Legal · Transparency">
      {OPERATOR_NOTICE}
      <Section title="Current product identity">
        <p><strong className="text-foreground">Product:</strong> SignalDesk</p>
        <p><strong className="text-foreground">Purpose:</strong> financial research and information for Indian equities</p>
        <p><strong className="text-foreground">Current commercial status:</strong> no paid products or checkout flow are implemented</p>
      </Section>
      <Section title="Details that must be supplied before public commercial launch">
        <ul className="list-disc space-y-2 pl-5">
          <li>Full legal entity or proprietor name.</li>
          <li>Registered/business address and jurisdiction.</li>
          <li>Dedicated privacy and legal/grievance contact details.</li>
          <li>GST/tax registration details if and when legally applicable to the business.</li>
          <li>Payment, cancellation, refund, and consumer-support details before any paid launch.</li>
          <li>SEBI registration/disclosure details if the service becomes regulated research or advisory activity.</li>
        </ul>
      </Section>
      <Section title="Why this page exists">
        <p>Legal identity is deliberately not guessed from a developer account or repository owner. Publishing a person's private contact details, inventing a company name, or inventing a registered address would create a more serious accuracy and privacy problem than leaving the field explicitly incomplete.</p>
      </Section>
      <Links />
    </LegalShell>
  );
}

export default function LegalPage({ kind }: { kind: LegalPageKind }) {
  if (kind === "privacy") return <PrivacyPolicy />;
  if (kind === "terms") return <Terms />;
  if (kind === "cookies") return <Cookies />;
  if (kind === "refund") return <Refunds />;
  return <LegalDetails />;
}
