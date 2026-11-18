{{- /*
Name of a Deployment rendered by the registry subchart, for wrapper resources that target it (autoscaling.yaml).
Same rule as the subchart's common.names.fullname: fullnameOverride, else the release name when it already contains
the component name, else "<release>-<nameOverride>" (e.g. farmer-registry-staff-portal-api).
Call: include "oan.registryComponentFullname" (dict "values" .Values.registry.staffApi "context" $)
*/ -}}
{{- define "oan.registryComponentFullname" -}}
{{- $v := .values -}}
{{- if $v.fullnameOverride -}}
{{- $v.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := required "registry component needs nameOverride" $v.nameOverride -}}
{{- if contains $name .context.Release.Name -}}
{{- .context.Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .context.Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}
