import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { copyFile } from 'node:fs/promises'

function replaceExactly(source, oldText, newText, expected, file) {
  const count = source.split(oldText).length - 1
  if (count !== expected) throw new Error(`${file}: expected ${expected} occurrences of ${JSON.stringify(oldText)}, found ${count}`)
  return source.split(oldText).join(newText)
}

export function transformIdentity(source, id, frontend) {
  if (id.includes('?')) return null
  if (!frontend) throw new Error('Expected HRMS frontend root')
  const file = path.resolve(id)
  const root = path.resolve(frontend)
  const enabled = 'ocean6Brand'
  const targets = ['src/components/BaseLayout.vue', 'src/components/InstallPrompt.vue', 'src/views/Login.vue'].map(p => path.join(root, p))
  if (!targets.includes(file)) return null
  if (source.includes('const ocean6Brand')) throw new Error(`${file}: identity binding already exists`)
  source = replaceExactly(source, '<script setup>', `<script setup>\nconst ocean6Brand = document.documentElement.dataset.ocean6Brand === 'true'`, 1, file)
  if (file === targets[0]) {
    source = replaceExactly(source, '{{ props.pageTitle || __("Frappe HR") }}', `<img v-if="${enabled}" :src="'/assets/malaysia_workforce/images/ocean6/icon.png'" alt="" aria-hidden="true" class="inline-block h-6 w-6 mr-2 align-middle" />{{ props.pageTitle || (${enabled} ? __("Ocean 6 HR") : __("Frappe HR")) }}`, 1, file)
  } else if (file === targets[1]) {
    source = replaceExactly(source, '__("Install Frappe HR")', `${enabled} ? __("Install Ocean 6 HR") : __("Install Frappe HR")`, 2, file)
  } else if (file === targets[2]) {
    source = replaceExactly(source, "const ocean6Brand = document.documentElement.dataset.ocean6Brand === 'true'", "const ocean6Brand = document.documentElement.dataset.ocean6Brand === 'true'\nconst ocean6EmailLink = document.documentElement.dataset.ocean6EmailLink === 'true'", 1, file)
    source = replaceExactly(source, 'v-else-if="user_pass_login_disabled.data"', 'v-else-if="user_pass_login_disabled.data && !(ocean6Brand && ocean6EmailLink)"', 1, file)
    source = replaceExactly(source, '<template v-if="authProviders.data?.length">', `<a v-if="ocean6Brand && ocean6EmailLink" class="ocean6-email-link" href="/login?redirect-to=%2Fhrms%2Fhome#login-with-email-link">{{ __("Login with Email Link") }}</a>\n\t\t\t\t\t<template v-if="authProviders.data?.length">`, 1, file)
    source = replaceExactly(source, ':loading="session.login.loading"\n\t\t\t\t\t\t\tvariant="solid"\n\t\t\t\t\t\t\tclass="disabled:bg-gray-700 disabled:text-white !mt-6"', ':loading="session.login.loading"\n\t\t\t\t\t\t\tvariant="solid"\n\t\t\t\t\t\t\tclass="disabled:bg-gray-700 disabled:text-white !mt-6 ocean6-hrms-login-submit"', 1, file)
    source = replaceExactly(source, '<div v-else class="flex h-screen w-screen flex-col justify-center bg-white">', `<div v-else class="flex h-screen w-screen flex-col justify-center bg-white" :class="{ 'ocean6-hrms-login': ${enabled} }">`, 1, file)
    source = replaceExactly(source, '<div class="flex flex-col mx-auto gap-3 items-center">', `<div class="flex flex-col mx-auto gap-3 items-center" :class="{ 'ocean6-hrms-login-brand': ${enabled} }">`, 1, file)
    source = replaceExactly(source, '<FrappeHRLogo class="h-8 w-8" />', `<img v-if="${enabled}" :src="'/assets/malaysia_workforce/images/ocean6/wordmark.png'" alt="Ocean 6" class="h-8 w-auto" /><FrappeHRLogo v-else class="h-8 w-8" />`, 1, file)
    source = replaceExactly(source, '__("Login to Frappe HR")', `${enabled} ? __("Ocean 6 HR") : __("Login to Frappe HR")`, 1, file)
  } else return null
  return { code: source, map: null }
}

async function main(frontend) {
  if (!frontend) throw new Error('Expected HRMS frontend path')
  frontend = path.resolve(frontend)
  process.chdir(frontend)
  const { build, mergeConfig, loadConfigFromFile } = await import(pathToFileURL(path.join(frontend, 'node_modules/vite/dist/node/index.js')).href)
  const loaded = await loadConfigFromFile({ command: 'build', mode: 'production' }, path.join(frontend, 'vite.config.js'), frontend)
  if (!loaded) throw new Error('Unable to load HRMS Vite configuration')
  const config = loaded.config
  await build(mergeConfig(config, {
    configFile: false,
    base: '/assets/hrms/frontend/',
    plugins: [{ name: 'ocean6-hrms-identity', enforce: 'pre', transform: (source, id) => transformIdentity(source, id, frontend) }],
  }))
  await copyFile(path.join(frontend, '../hrms/public/frontend/index.html'), path.join(frontend, '../hrms/www/hrms.html'))
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  main(process.argv[2]).catch(error => { console.error(error); process.exitCode = 1 })
}
