set.seed(20260806)

source("assets/r_methods.R")

stopifnot(
  weighted_linear_quantile(c(1, 2, 3), c(1, 8, 1), .50) == 2,
  isTRUE(all.equal(
    weighted_linear_quantile(c(1, 2, 2, 3), c(1, 2, 3, 1), .75),
    31 / 12
  ))
)

n <- 240L
psu <- rep(seq_len(24L), each = 10L)
dat <- data.frame(
  psu = psu,
  strata = factor(rep(rep(letters[1:4], each = 6L), each = 10L)),
  final_weight = stats::runif(n, .5, 2),
  exposure = stats::rnorm(n),
  modifier = factor(rep(c("reference", "index"), length.out = n)),
  age = stats::rnorm(n, 70, 5)
)
dat$outcome_interaction <- .2 + .45 * dat$exposure +
  .75 * dat$exposure * (dat$modifier == "index") + .02 * dat$age + stats::rnorm(n)
dat$outcome_curve <- .3 + .5 * dat$exposure + .45 * dat$exposure^2 +
  .02 * dat$age + stats::rnorm(n)

for (mode in c("sample", "survey_weight_only", "survey_full")) {
  weight_var <- if (mode == "sample") NULL else "final_weight"
  strata_var <- if (mode == "survey_full") "strata" else NULL
  psu_var <- if (mode == "survey_full") "psu" else NULL

  interaction_dir <- tempfile(paste0("interaction_", mode, "_"))
  interaction <- fit_weighted_interaction_continuous(
    dat, "outcome_interaction", "exposure", "modifier", "age", interaction_dir,
    weight_var = weight_var, strata_var = strata_var, psu_var = psu_var,
    design_mode = mode, grid_points = 11L
  )
  stopifnot(
    inherits(interaction$model, if (mode == "sample") "lm" else "svyglm"),
    nrow(interaction$coefficients) >= 2L,
    nrow(interaction$predictions) == 22L,
    nrow(interaction$support) == 2L,
    is.finite(interaction$joint_test$p_value),
    interaction$joint_test$status == "ESTIMATED_WALD_F",
    file.exists(interaction$figure)
  )
  if (mode == "survey_weight_only") {
    stopifnot(all(grepl("FORMAL_SURVEY_VARIANCE_UNAVAILABLE", interaction$predictions$variance_status)))
  }

  dose_dir <- tempfile(paste0("dose_", mode, "_"))
  dose <- run_weighted_rcs_dose_response(
    dat, "outcome_curve", "exposure", "age", dose_dir,
    weight_var = weight_var, strata_var = strata_var, psu_var = psu_var,
    design_mode = mode, grid_points = 15L
  )
  stopifnot(
    inherits(dose$model, if (mode == "sample") "lm" else "svyglm"),
    nrow(dose$coefficients) == 3L,
    nrow(dose$predictions) == 15L,
    identical(dose$tests$test, c("dose_response_overall", "dose_response_nonlinearity")),
    all(is.finite(dose$tests$p_value)),
    all(dose$tests$status == "ESTIMATED_WALD_F"),
    all(diff(dose$knots) > 0),
    max(abs(dose$predictions$contrast_to_reference[
      which.min(abs(dose$predictions$exposure_value - dose$reference_value))
    ])) < .15,
    file.exists(dose$figure)
  )
  generated_csv <- c(
    list.files(file.path(interaction_dir, "tables"), full.names = TRUE),
    list.files(file.path(dose_dir, "tables"), full.names = TRUE)
  )
  stopifnot(length(generated_csv) == 8L)
  generated_text <- paste(vapply(generated_csv, function(path) {
    paste(readLines(path, warn = FALSE), collapse = "\n")
  }, character(1)), collapse = "\n")
  stopifnot(!grepl("placeholder", generated_text, ignore.case = TRUE))
}

dat$modifier_numeric <- stats::rnorm(n)
dat$outcome_numeric_interaction <- .4 * dat$exposure +
  .6 * dat$exposure * dat$modifier_numeric + .02 * dat$age + stats::rnorm(n)
numeric_interaction <- fit_weighted_interaction_continuous(
  dat, "outcome_numeric_interaction", "exposure", "modifier_numeric", "age",
  tempfile("interaction_numeric_"), design_mode = "sample", grid_points = 11L
)
stopifnot(
  nrow(numeric_interaction$predictions) == 33L,
  nrow(numeric_interaction$support) == 1L,
  is.finite(numeric_interaction$joint_test$p_value)
)

cat("METHOD_LIBRARY_SMOKE=PASS\n")
