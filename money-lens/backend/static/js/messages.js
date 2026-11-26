/* Human-readable wording for every problem the backend or browser can report. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else { root.MoneyLens = root.MoneyLens || {}; root.MoneyLens.messages = factory(); }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var READ_FAIL = "We couldn't read this statement.";

  var TABLE = {
    missing_file: ['No file selected', 'Choose a PDF or CSV statement to continue.'],
    empty_file: ['This file is empty', 'Please choose your statement file and try again.'],
    file_too_large: ['This file is too large', 'Please choose a smaller file{max}.'],
    unsupported_type: ['Unsupported file', 'Only PDF and CSV statements are supported. Please choose a .pdf or .csv file.'],
    content_mismatch: ["This file doesn't look right", "The file doesn't look like a valid PDF or CSV. Please download your statement again and try once more."],
    multiple_files: ['One file at a time', 'Please choose a single statement file.'],
    duplicate_upload: ['Already uploading', 'This statement is already being processed.'],

    pdf_no_text: [READ_FAIL, 'Please check that the PDF contains selectable text and try again.'],
    pdf_unreadable: [READ_FAIL, "The PDF may be damaged or password protected. Remove any password, or download the statement again, then try once more."],
    pdf_encrypted: [READ_FAIL, 'This PDF is password protected. Remove the password and try again.'],
    csv_unreadable: [READ_FAIL, 'The CSV file could not be read. Please download it again and try once more.'],
    csv_no_header: ["We couldn't find your transactions", "We couldn't find a table with date and amount columns in this file. Please check it's a bank statement export."],
    no_transactions: ["We couldn't find any transactions", "Nothing in this file could be read as a transaction. Please check it's the right statement."],
    multiple_currencies: ['More than one currency', "This statement contains more than one currency, which we can't report on yet."],

    not_allowed: ["This upload can't be processed", 'It may have expired or already been processed. Please upload your statement again.'],
    expired: ['This upload expired', 'Please upload your statement again.'],
    session_expired: ['Your session has expired', 'Please log in again to continue. Your file has not been saved.'],
    network_error: ["We couldn't reach the server", 'Please check your connection and try again.'],
    internal_error: ['Something went wrong', "Something went wrong on our side. Please try again in a moment."]
  };

  /** @returns {{title: string, message: string}} */
  function describe(code, context) {
    var entry = TABLE[code] || TABLE.internal_error;
    var max = context && context.maxLabel ? ' (up to ' + context.maxLabel + ')' : '';
    return { title: entry[0], message: entry[1].replace('{max}', max) };
  }

  return { describe: describe, codes: Object.keys(TABLE) };
});
