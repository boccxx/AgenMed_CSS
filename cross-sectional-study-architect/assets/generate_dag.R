#!/usr/bin/env Rscript

suppressPackageStartupMessages(require(dagitty))

args <- commandArgs(trailingOnly = TRUE)
nodes_path <- if (length(args) >= 1) args[[1]] else "nodes.csv"
edges_path <- if (length(args) >= 2) args[[2]] else "edges.csv"
prefix <- if (length(args) >= 3) args[[3]] else "dag"
out_dir <- if (length(args) >= 4) args[[4]] else getwd()

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

make_dag <- function(edges) {
  dagitty(sprintf("dag { %s }", paste(edges, collapse = " ; ")))
}

read_edges <- function(path) {
  if (!file.exists(path)) return(NULL)
  data <- tryCatch(read.csv(path, stringsAsFactors = FALSE), error = function(e) NULL)
  if (is.null(data) || ncol(data) < 2) return(NULL)
  as.character(sprintf("%s -> %s", data[[1]], data[[2]]))
}

read_nodes <- function(path) {
  if (!file.exists(path)) return(NULL)
  data <- tryCatch(read.csv(path, stringsAsFactors = FALSE), error = function(e) NULL)
  if (is.null(data) || ncol(data) < 1) return(NULL)
  nodes <- as.character(data[[1]])
  if (length(nodes) < 2) return(NULL)
  c(
    sprintf("%s -> %s", nodes[[1]], nodes[[2]]),
    sprintf("%s -> %s", nodes[[1]], nodes[-c(1, 2)])
  )
}

edges <- read_edges(edges_path)
if (is.null(edges)) edges <- read_nodes(nodes_path)
if (is.null(edges)) stop("Provide an edges.csv or a nodes.csv with at least two nodes.")

dag <- make_dag(edges)
user_script <- file.path(getwd(), "dag代码.R")
png_path <- file.path(out_dir, paste0(prefix, ".png"))
pdf_path <- file.path(out_dir, paste0(prefix, ".pdf"))

if (file.exists(user_script)) {
  env <- new.env(parent = globalenv())
  assign("dag_obj", dag, envir = env)
  assign("out_prefix", prefix, envir = env)
  assign("out_dir", out_dir, envir = env)
  sys.source(user_script, envir = env)
  if (exists("plot_user_dag", envir = env)) {
    get("plot_user_dag", envir = env)(dag, prefix)
    quit(save = "no", status = 0)
  }
}

png(png_path, width = 3000, height = 3000, res = 300)
plot(dag, main = prefix)
dev.off()

pdf(pdf_path, width = 11, height = 11)
plot(dag, main = prefix)
dev.off()

cat(sprintf("Generated %s and %s\n", png_path, pdf_path))
