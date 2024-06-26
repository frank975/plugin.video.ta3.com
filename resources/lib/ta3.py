# -*- coding: UTF-8 -*-
# /*
# *      Copyright (C) 2014 Maros Ondrasek
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# */
import calendar
import urllib.request, urllib.parse, urllib.error
import urllib.parse
import re
import http.cookiejar
from datetime import date
import xbmc
import util
from provider import ContentProvider


class TA3ContentProvider(ContentProvider):

    def __init__(self, username=None, password=None, filter=None, tmp_dir='/tmp'):
        ContentProvider.__init__(self, 'ta3.com', 'https://www.ta3.com/', username, password, filter, tmp_dir)
        self.cp = urllib.request.HTTPCookieProcessor(http.cookiejar.LWPCookieJar())
        self.init_urllib()

    def init_urllib(self):
        opener = urllib.request.build_opener(self.cp)
        urllib.request.install_opener(opener)

    def capabilities(self):
        return ['categories', 'resolve', '!download']

    def categories(self):
        result = []
        item = self.video_item()
        item['title'] = 'Live'
        item['url'] = "live.html"
        result.append(item)
        result.append(self.dir_item('Relácie', self.base_url + 'archiv#mycat'))
        return result

    def list(self, url):

        purl = urllib.parse.urlparse(url)
        if url.find("#") != -1:
            url = url[:url.find("#")]

        # this is special for kodi
        if purl.fragment == "mycat":
            url = url.split("#")[0]
            result = []
            #result.append(self.dir_item(url=url, type='new'))
            result.extend(self.list_categories(url))
            return result
            
        if 'archiv?page=' in url:
            result = []
            result.extend(self.list_categories(url))
            return result
         
        return self.list_videos(self._url(url))

    def list_categories(self, url):
        result = []
        page = util.request(url)
        if 'archiv' in url:
            start = '<main class="tvshows_listing">'
        else:
            self.error("_list_categories: unknown category url: %s" % url)
            return []
        data = util.substr(page, start, '</main>')
        for m in re.finditer('<a\ href=\"(?P<url>[^\"]+)\"\ class.*?<h4>(?P<title>[^<]+)<\/h4>', data, re.DOTALL):
            item = self.dir_item()
            item['url'] = self.base_url + m.group('url') 
            item['title'] = m.group('title')
            self._filter(result, item)
        pager_data = util.substr(page,'<div class="pagination-wrap"', '</div>')
        next_page_match = re.search(r'<a class="page-link" href="(?P<url>[^"]+)" rel="next"', pager_data)
        if next_page_match:
            item = self.dir_item()
            item['type'] = 'next'
            item['url'] = next_page_match.group('url').replace('&amp;','&')
            self._filter(result, item)
        return result

    def list_videos(self, url):
        result = []
        page = util.request(url)
        if '?page=' in url:
             data = util.substr(page, '<h4 class="archive-loop-title">Ďalšie v archíve</h4>','</main>')
        else:
             data = util.substr(page, '<main class="tvshow"','</main>')
        listing_iter_re = r'<a href=\"(?P<url>[^\"]*)\">(?P<title>[^<]*?)<\/a>\s+<\/h2>'
        for m in re.finditer(listing_iter_re, data, re.DOTALL ):
            item = self.video_item()
            item['title'] = m.group('title').strip()
            item['url'] = m.group('url')
            self._filter(result, item)
        pager_data = util.substr(page,'<div class="pagination-wrap"', '</div>')
        next_page_match = re.search(r'<a class="page-link" href="(?P<url>[^"]+)" rel="next"', pager_data)
        if next_page_match:
            item = self.dir_item()
            item['type'] = 'next'
            item['url'] = next_page_match.group('url').replace('&amp;','&')
            self._filter(result, item)
        return result

    def resolve(self, item, captcha_cb=None, select_cb=None):
       item = item.copy()
       if 'live.html' in item['url']:
           result = self._resolve_live(item)
           result = sorted(result, key=lambda x:x['quality'], reverse=True)
       else:
           result = self._resolve_vod(item)
       if len(result) > 0 and select_cb:
           return select_cb(result)
       return result

    def _resolve_vod(self, item):
        resolved = []
        data = util.request(self._url(item['url']))
        video_id = re.search("LiveboxPlayer.archiv\(.+?\"videoId\":*\"([^\"]+)\"", data, re.DOTALL).group(1)
        player_data = util.request("http://embed.livebox.cz/ta3_v2/vod-source.js", {'Referer':self._url(item['url'])})
        url_format = re.search(r'my.embedurl = \[\{"src" : "([^"]+)"', player_data).group(1)
        manifest_url = "https:" + url_format.format(video_id)
        manifest_url = urllib.request.urlopen(manifest_url).geturl()
        manifest = util.request(manifest_url)
        xbmc.log("manifest " + manifest)
        for m in re.finditer('#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=(?P<bandwidth>\d+).*?(,RESOLUTION=(?P<resolution>\d+x\d+))?\s(?P<chunklist>[^\s]+)', manifest, re.DOTALL):
            item = self.video_item()
            item['surl'] = item['title']
            item['quality'] = m.group('bandwidth')
            item['url'] = urllib.parse.urljoin(manifest_url, m.group('chunklist'))
            resolved.append(item)
        resolved = sorted(resolved, key=lambda x:int(x['quality']), reverse=True)
        if len(resolved) == 3:
            qualities = ['720p', '480p', '360p']
            for idx, item in enumerate(resolved):
                item['quality'] = qualities[idx]
        else:
            for idx, item in enumerate(resolved):
                item['quality'] += 'b/s'
        return resolved

    def _resolve_live(self, item):
        resolved = []
        data = util.request(self._url(item['url']))
        player_data = util.request("https://embed.livebox.cz/ta3_v2/live-source.js", {'Referer':self._url(item['url'])})
        for m_manifest in re.finditer(r'\{"src"\s*:\s*"([^"]+)"\s*\}', player_data, re.DOTALL):
            manifest_url = m_manifest.group(1)
            if manifest_url.startswith('//'):
               manifest_url = 'https:'+ manifest_url
            req = urllib.request.Request(manifest_url)
            resp = urllib.request.urlopen(req)
            manifest = resp.read().decode('utf-8')
            resp.close()
            for m in re.finditer('RESOLUTION=\d+x(?P<resolution>\d+)\s+(?P<chunklist>[^\s]+)', manifest, re.DOTALL):
                item = self.video_item()
                item['surl'] = item['title']
                item['quality'] = m.group('resolution') + 'p'
                item['url'] = urllib.parse.urljoin(resp.geturl(), m.group('chunklist'))
                resolved.append(item)
            # only first manifest url looks to be is valid
            break
        return resolved
