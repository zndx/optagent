module zndx.org/optagent/ui

go 1.27.2

require go.kenn.io/agentsview v0.0.0

// Editable checkout. Edits in this working tree are the agentsview this
// module builds. Do not replace this with a released version.
replace go.kenn.io/agentsview => ../../../rch/oss-agentsview
