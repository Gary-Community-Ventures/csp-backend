-- 001_analytics_schema.sql
-- Curated views for Scry's AI service.
--
-- These views are intentionally analysis-first and PII-light. They omit raw
-- names, emails, phone numbers, addresses, exact dates of birth, Chek IDs,
-- provider message IDs, email bodies, and invite emails.
--
-- Sourced from scry/db/migrations/001_analytics_schema.sql. The original
-- BEGIN/COMMIT wrapper is intentionally omitted here: this file is executed
-- inside an Alembic-managed transaction (see
-- migrations/versions/802e3181c595_create_analytics_schema_views.py).

CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA analytics IS
  'Curated read-only reporting surface for Scry natural-language analytics.';

DO $$
BEGIN
  IF to_regclass('public.family') IS NOT NULL THEN
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.families
      WITH (security_barrier = true) AS
      SELECT
        f.id AS family_id,
        f.created_at,
        f.referred_by,
        f.size AS family_size,
        CASE
          WHEN f.yearly_income IS NULL THEN NULL
          WHEN f.yearly_income < 25000 THEN '<25k'
          WHEN f.yearly_income < 50000 THEN '25k-50k'
          WHEN f.yearly_income < 75000 THEN '50k-75k'
          WHEN f.yearly_income < 100000 THEN '75k-100k'
          ELSE '100k+'
        END AS yearly_income_band,
        f.zip AS family_zip,
        f.language,
        f.portal_invite_sent_at IS NOT NULL AS portal_invite_sent,
        f.provider_invited_at IS NOT NULL AS provider_invited,
        f.provider_approved_at IS NOT NULL AS provider_approved,
        f.first_payment_sent_at
      FROM public.family f
    $view$;
  ELSE
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.families
      WITH (security_barrier = true) AS
      SELECT
        NULL::text AS family_id,
        NULL::timestamp with time zone AS created_at,
        NULL::text AS referred_by,
        NULL::integer AS family_size,
        NULL::text AS yearly_income_band,
        NULL::text AS family_zip,
        NULL::text AS language,
        NULL::boolean AS portal_invite_sent,
        NULL::boolean AS provider_invited,
        NULL::boolean AS provider_approved,
        NULL::timestamp with time zone AS first_payment_sent_at
      WHERE false
    $view$;
  END IF;
END
$$;

DO $$
BEGIN
  IF to_regclass('public.child') IS NOT NULL THEN
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.children
      WITH (security_barrier = true) AS
      SELECT
        c.id AS child_id,
        c.family_id,
        c.created_at,
        CASE
          WHEN c.dob IS NULL THEN NULL
          ELSE date_part('year', age(current_date, c.dob))::int
        END AS age_years,
        c.status,
        c.payment_enabled,
        round(c.monthly_allocation::numeric, 2) AS monthly_allocation_dollars,
        round(c.prorated_allocation::numeric, 2) AS prorated_allocation_dollars
      FROM public.child c
    $view$;
  ELSE
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.children
      WITH (security_barrier = true) AS
      SELECT
        NULL::text AS child_id,
        NULL::text AS family_id,
        NULL::timestamp with time zone AS created_at,
        NULL::integer AS age_years,
        NULL::text AS status,
        NULL::boolean AS payment_enabled,
        NULL::numeric AS monthly_allocation_dollars,
        NULL::numeric AS prorated_allocation_dollars
      WHERE false
    $view$;
  END IF;
END
$$;

DO $$
BEGIN
  IF to_regclass('public.provider') IS NOT NULL THEN
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.providers
      WITH (security_barrier = true) AS
      SELECT
        p.id AS provider_id,
        p.created_at,
        p.status,
        p.type AS provider_type,
        p.payment_enabled,
        p.care_location_city AS city,
        p.care_location_state AS state,
        p.care_location_zip AS zip,
        p.preferred_language,
        p.cpr_certified,
        p.cpr_online_training_completed_at IS NOT NULL AS cpr_online_training_completed,
        p.child_safety_module_training_completed_at IS NOT NULL AS child_safety_module_training_completed,
        p.safe_sleep_for_infants_training_completed_at IS NOT NULL AS safe_sleep_training_completed,
        p.home_safety_and_injury_prevention_training_completed_at IS NOT NULL AS home_safety_training_completed,
        p.pdis_first_aid_cpr_completed_at IS NOT NULL AS pdis_first_aid_cpr_completed,
        p.pdis_standard_precautions_completed_at IS NOT NULL AS pdis_standard_precautions_completed,
        p.pdis_preventing_child_abuse_completed_at IS NOT NULL AS pdis_preventing_child_abuse_completed,
        p.pdis_infant_safe_sleep_completed_at IS NOT NULL AS pdis_infant_safe_sleep_completed,
        p.pdis_emergency_preparedness_completed_at IS NOT NULL AS pdis_emergency_preparedness_completed,
        p.pdis_injury_prevention_completed_at IS NOT NULL AS pdis_injury_prevention_completed,
        p.pdis_preventing_shaken_baby_completed_at IS NOT NULL AS pdis_preventing_shaken_baby_completed,
        p.pdis_recognizing_impact_of_bias_completed_at IS NOT NULL AS pdis_recognizing_impact_of_bias_completed,
        p.pdis_medication_administration_part_one_completed_at IS NOT NULL AS pdis_medication_administration_part_one_completed,
        p.portal_invite_sent_at IS NOT NULL AS portal_invite_sent,
        p.family_invited_at IS NOT NULL AS family_invited,
        p.rates_configured_at IS NOT NULL AS rates_configured,
        p.payment_method_configured_at IS NOT NULL AS payment_method_configured,
        p.first_payment_received_at
      FROM public.provider p
    $view$;
  ELSE
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.providers
      WITH (security_barrier = true) AS
      SELECT
        NULL::text AS provider_id,
        NULL::timestamp with time zone AS created_at,
        NULL::text AS status,
        NULL::text AS provider_type,
        NULL::boolean AS payment_enabled,
        NULL::text AS city,
        NULL::text AS state,
        NULL::text AS zip,
        NULL::text AS preferred_language,
        NULL::boolean AS cpr_certified,
        NULL::boolean AS cpr_online_training_completed,
        NULL::boolean AS child_safety_module_training_completed,
        NULL::boolean AS safe_sleep_training_completed,
        NULL::boolean AS home_safety_training_completed,
        NULL::boolean AS pdis_first_aid_cpr_completed,
        NULL::boolean AS pdis_standard_precautions_completed,
        NULL::boolean AS pdis_preventing_child_abuse_completed,
        NULL::boolean AS pdis_infant_safe_sleep_completed,
        NULL::boolean AS pdis_emergency_preparedness_completed,
        NULL::boolean AS pdis_injury_prevention_completed,
        NULL::boolean AS pdis_preventing_shaken_baby_completed,
        NULL::boolean AS pdis_recognizing_impact_of_bias_completed,
        NULL::boolean AS pdis_medication_administration_part_one_completed,
        NULL::boolean AS portal_invite_sent,
        NULL::boolean AS family_invited,
        NULL::boolean AS rates_configured,
        NULL::boolean AS payment_method_configured,
        NULL::timestamp with time zone AS first_payment_received_at
      WHERE false
    $view$;
  END IF;
END
$$;

DO $$
BEGIN
  IF to_regclass('public.provider_child_mapping') IS NOT NULL THEN
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.provider_child_relationships
      WITH (security_barrier = true) AS
      SELECT
        pcm.id AS relationship_id,
        pcm.created_at,
        pcm.provider_id,
        pcm.child_id
      FROM public.provider_child_mapping pcm
    $view$;
  ELSE
    EXECUTE $view$
      CREATE OR REPLACE VIEW analytics.provider_child_relationships
      WITH (security_barrier = true) AS
      SELECT
        NULL::text AS relationship_id,
        NULL::timestamp with time zone AS created_at,
        NULL::text AS provider_id,
        NULL::text AS child_id
      WHERE false
    $view$;
  END IF;
END
$$;

CREATE OR REPLACE VIEW analytics.monthly_allocations
WITH (security_barrier = true) AS
SELECT
  ma.id AS month_allocation_id,
  ma.child_supabase_id AS child_id,
  ma.date AS allocation_month,
  round(ma.allocation_cents::numeric / 100.0, 2) AS allocation_dollars,
  ma.chek_transfer_date,
  ma.chek_transfer_id IS NOT NULL AS transfer_created,
  ma.created_at,
  ma.updated_at
FROM public.month_allocation ma;

CREATE OR REPLACE VIEW analytics.care_days
WITH (security_barrier = true) AS
SELECT
  acd.id AS care_day_id,
  ma.child_supabase_id AS child_id,
  acd.provider_supabase_id AS provider_id,
  acd.care_month_allocation_id AS month_allocation_id,
  ma.date AS allocation_month,
  acd.date AS care_date,
  acd.type AS care_day_type,
  round(acd.amount_cents::numeric / 100.0, 2) AS amount_dollars,
  round(acd.amount_missing_cents::numeric / 100.0, 2) AS amount_missing_dollars,
  acd.payment_distribution_requested,
  acd.payment_id IS NOT NULL AS paid,
  acd.last_submitted_at,
  acd.deleted_at IS NOT NULL AS deleted,
  acd.created_at,
  acd.updated_at
FROM public.allocated_care_day acd
JOIN public.month_allocation ma
  ON ma.id = acd.care_month_allocation_id;

CREATE OR REPLACE VIEW analytics.lump_sums
WITH (security_barrier = true) AS
SELECT
  als.id AS lump_sum_id,
  ma.child_supabase_id AS child_id,
  als.provider_supabase_id AS provider_id,
  als.care_month_allocation_id AS month_allocation_id,
  ma.date AS allocation_month,
  round(als.amount_cents::numeric / 100.0, 2) AS amount_dollars,
  als.days,
  als.half_days,
  als.payment_id IS NOT NULL OR als.paid_at IS NOT NULL AS paid,
  als.submitted_at,
  als.created_at,
  als.updated_at
FROM public.allocated_lump_sum als
JOIN public.month_allocation ma
  ON ma.id = als.care_month_allocation_id;

CREATE OR REPLACE VIEW analytics.payments
WITH (security_barrier = true) AS
SELECT
  p.id AS payment_id,
  p.payment_intent_id,
  p.provider_supabase_id AS provider_id,
  p.child_supabase_id AS child_id,
  p.month_allocation_id,
  ma.date AS allocation_month,
  round(p.amount_cents::numeric / 100.0, 2) AS amount_dollars,
  p.payment_method,
  'successful'::text AS payment_status,
  p.created_at,
  p.updated_at
FROM public.payment p
LEFT JOIN public.month_allocation ma
  ON ma.id = p.month_allocation_id;

CREATE OR REPLACE VIEW analytics.payment_intents
WITH (security_barrier = true) AS
SELECT
  pi.id AS payment_intent_id,
  pi.provider_supabase_id AS provider_id,
  pi.child_supabase_id AS child_id,
  pi.month_allocation_id,
  ma.date AS allocation_month,
  round(pi.amount_cents::numeric / 100.0, 2) AS amount_dollars,
  jsonb_array_length(coalesce(pi.care_day_ids::jsonb, '[]'::jsonb)) AS care_day_count,
  jsonb_array_length(coalesce(pi.lump_sum_ids::jsonb, '[]'::jsonb)) AS lump_sum_count,
  p.id IS NOT NULL AS paid,
  count(pa.id) AS attempt_count,
  pi.created_at,
  pi.updated_at
FROM public.payment_intent pi
LEFT JOIN public.payment p
  ON p.payment_intent_id = pi.id
LEFT JOIN public.payment_attempt pa
  ON pa.payment_intent_id = pi.id
LEFT JOIN public.month_allocation ma
  ON ma.id = pi.month_allocation_id
GROUP BY
  pi.id,
  ma.date,
  p.id;

CREATE OR REPLACE VIEW analytics.payment_attempts
WITH (security_barrier = true) AS
SELECT
  pa.id AS payment_attempt_id,
  pa.payment_intent_id,
  pi.provider_supabase_id AS provider_id,
  pi.child_supabase_id AS child_id,
  pa.attempt_number,
  pa.payment_method,
  CASE
    WHEN pa.ach_payment_id IS NOT NULL OR pa.card_transfer_id IS NOT NULL THEN 'success'
    WHEN pa.error_message IS NOT NULL THEN 'failed'
    WHEN pa.wallet_transfer_id IS NOT NULL THEN 'wallet_funded'
    ELSE 'pending'
  END AS attempt_status,
  pa.wallet_transfer_at,
  pa.ach_payment_at,
  pa.card_transfer_at,
  pa.error_message IS NOT NULL AS has_error,
  pa.created_at,
  pa.updated_at
FROM public.payment_attempt pa
JOIN public.payment_intent pi
  ON pi.id = pa.payment_intent_id;

CREATE OR REPLACE VIEW analytics.payment_rates
WITH (security_barrier = true) AS
SELECT
  pr.id AS payment_rate_id,
  pr.provider_supabase_id AS provider_id,
  pr.child_supabase_id AS child_id,
  round(pr.half_day_rate_cents::numeric / 100.0, 2) AS half_day_rate_dollars,
  round(pr.full_day_rate_cents::numeric / 100.0, 2) AS full_day_rate_dollars,
  pr.created_at,
  pr.updated_at
FROM public.payment_rate pr;

CREATE OR REPLACE VIEW analytics.attendance_weeks
WITH (security_barrier = true) AS
SELECT
  a.id AS attendance_id,
  a.week,
  a.child_supabase_id AS child_id,
  a.provider_supabase_id AS provider_id,
  a.family_entered_full_days,
  a.family_entered_half_days,
  a.family_entered_at,
  a.family_opened_at,
  a.provider_entered_full_days,
  a.provider_entered_half_days,
  a.provider_entered_at,
  a.provider_opened_at,
  a.created_at,
  a.updated_at
FROM public.attendance a;

CREATE OR REPLACE VIEW analytics.fund_reclamations
WITH (security_barrier = true) AS
SELECT
  fr.id AS fund_reclamation_id,
  fr.month_allocation_id,
  ma.child_supabase_id AS child_id,
  ma.date AS allocation_month,
  round(fr.amount_cents::numeric / 100.0, 2) AS amount_dollars,
  fr.chek_transfer_id IS NOT NULL AS transfer_created,
  fr.created_at,
  fr.updated_at
FROM public.fund_reclamation fr
LEFT JOIN public.month_allocation ma
  ON ma.id = fr.month_allocation_id;

CREATE OR REPLACE VIEW analytics.invitation_engagement
WITH (security_barrier = true) AS
SELECT
  'family_invitation'::text AS invitation_type,
  fi.id::text AS invitation_id,
  fi.provider_supabase_id AS provider_id,
  NULL::text AS child_id,
  fi.email_sent,
  fi.sms_sent,
  fi.accepted,
  fi.opened_at,
  fi.created_at,
  fi.updated_at
FROM public.family_invitation fi
UNION ALL
SELECT
  'provider_invitation'::text AS invitation_type,
  pi.id::text AS invitation_id,
  NULL::text AS provider_id,
  pi.child_supabase_id AS child_id,
  pi.email_sent,
  pi.sms_sent,
  pi.accepted,
  pi.opened_at,
  pi.created_at,
  pi.updated_at
FROM public.provider_invitation pi;

CREATE OR REPLACE VIEW analytics.user_activity_by_hour
WITH (security_barrier = true) AS
SELECT
  ua.id AS user_activity_id,
  ua.hour,
  ua.provider_supabase_id AS provider_id,
  ua.family_supabase_id AS family_id,
  CASE
    WHEN ua.provider_supabase_id IS NOT NULL THEN 'provider'
    WHEN ua.family_supabase_id IS NOT NULL THEN 'family'
    ELSE 'unknown'
  END AS actor_type,
  ua.created_at,
  ua.updated_at
FROM public.user_activity ua;

CREATE OR REPLACE VIEW analytics.click_engagement
WITH (security_barrier = true) AS
SELECT
  c.id AS click_id,
  c.tracking_id,
  c.click_count,
  c.provider_supabase_id AS provider_id,
  c.family_supabase_id AS family_id,
  CASE
    WHEN c.provider_supabase_id IS NOT NULL THEN 'provider'
    WHEN c.family_supabase_id IS NOT NULL THEN 'family'
    ELSE 'unknown'
  END AS actor_type,
  CASE
    WHEN c.url IS NULL THEN NULL
    ELSE split_part(regexp_replace(c.url, '^https?://', ''), '/', 1)
  END AS url_host,
  c.created_at,
  c.updated_at
FROM public.click c;

CREATE OR REPLACE VIEW analytics.email_delivery_summary
WITH (security_barrier = true) AS
SELECT
  er.id AS email_record_id,
  er.status,
  er.attempt_count,
  er.email_provider,
  er.provider_status_code,
  er.email_type,
  er.is_internal,
  er.bulk_batch_id,
  cardinality(er.to_emails) AS recipients_count,
  er.last_attempt_at,
  er.created_at,
  er.updated_at
FROM public.email_record er;

CREATE OR REPLACE VIEW analytics.email_batches
WITH (security_barrier = true) AS
SELECT
  beb.id AS bulk_batch_id,
  beb.batch_name,
  beb.batch_type,
  beb.total_recipients,
  beb.successful_sends,
  beb.failed_sends,
  CASE
    WHEN beb.total_recipients = 0 THEN 0::numeric
    ELSE round((beb.successful_sends::numeric / beb.total_recipients::numeric) * 100.0, 2)
  END AS success_rate_percent,
  beb.status,
  beb.started_at,
  beb.completed_at,
  beb.created_at
FROM public.bulk_email_batch beb;

COMMENT ON VIEW analytics.families IS 'PII-light family enrollment and milestone facts.';
COMMENT ON VIEW analytics.children IS 'Child facts with age in years instead of exact DOB.';
COMMENT ON VIEW analytics.providers IS 'Provider readiness, location, type, and milestone facts without direct contact data.';
COMMENT ON VIEW analytics.payments IS 'Successful payment facts with dollar-normalized amounts.';
COMMENT ON VIEW analytics.email_delivery_summary IS 'Email delivery metrics without subjects, bodies, recipients, or provider message IDs.';
