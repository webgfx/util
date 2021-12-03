function getParamByName(name, url) {
  if (!url)
    url = window.location.href;
  name = name.replace(/[\[\]]/g, '\\$&');
  let regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)', 'i');
  let match = regex.exec(url);
  if (!match)
    return null;
  if (!match[2])
    return '';
  return decodeURIComponent(match[2].replace(/\+/g, ' '));
}

function readFile(file, callback) {
  let xhr = new XMLHttpRequest();
  xhr.overrideMimeType('application/json');
  xhr.open('GET', file, true);
  xhr.onreadystatechange = function () {
    if (xhr.readyState === 4 && xhr.status == '200') {
      callback(xhr.responseText);
    }
  };
  xhr.send();
}
