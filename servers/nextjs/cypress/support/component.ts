// ***********************************************************
// This example support/component.ts is processed and
// loaded automatically before your test files.
//
// This is a great place to put global configuration and
// behavior that modifies Cypress.
//
// You can change the location of this file or turn off
// automatically serving support files with the
// 'supportFile' configuration option.
//
// You can read more here:
// https://on.cypress.io/configuration
// ***********************************************************

// Import commands.js using ES2015 syntax:
import './commands'

import { createElement } from 'react'
import { mount } from 'cypress/react'
import { NextIntlClientProvider } from 'next-intl'

import messages from '../../messages/en.json'

// Augment the Cypress namespace to include type definitions for
// your custom command.
// Alternatively, can be defined in cypress/support/component.d.ts
// with a <reference path="./component" /> at the top of your spec.
declare global {
  namespace Cypress {
    interface Chainable {
      mount: typeof mount
    }
  }
}

// Components use next-intl; mount them inside the same provider the app root
// layout supplies, with the English catalog so existing assertions still hold.
Cypress.Commands.add('mount', ((component, options) =>
  mount(
    createElement(NextIntlClientProvider, {
      locale: 'en',
      messages,
      children: component,
    }),
    options,
  )) as typeof mount)

// Example use:
// cy.mount(<MyComponent />)