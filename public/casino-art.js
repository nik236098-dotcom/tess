'use strict';
const CasinoArt=(()=>{
const shapes={
 gem:'<path d="M30 44L52 21H108L130 44 80 117Z" fill="#8857d6"/><path d="M30 44H130M52 21L61 44 80 117 99 44 108 21M61 44H99"/>',
 cards:'<g transform="rotate(-12 65 76)"><rect x="29" y="27" width="66" height="91" rx="9" fill="#281b46"/><path d="M46 49L57 35 68 49 57 63Z" fill="#c192ff"/></g><g transform="rotate(9 99 78)"><rect x="69" y="29" width="64" height="91" rx="9" fill="#f6efff"/><path d="M102 52C65 82 87 91 100 81V98H109V81C125 94 141 78 102 52Z" fill="#5d3285" stroke="none"/></g>',
 orbit:'<ellipse cx="80" cy="70" rx="62" ry="22" transform="rotate(-30 80 70)"/><circle cx="80" cy="70" r="33" fill="#593481"/><path d="M65 76L80 57 95 76M80 58V94"/><circle cx="134" cy="43" r="7" fill="#ffe1a1"/>',
 dice:'<g transform="rotate(-10 80 70)"><rect x="38" y="26" width="84" height="84" rx="17" fill="#c6a7f7"/><g fill="#28163d" stroke="none"><circle cx="60" cy="48" r="6"/><circle cx="100" cy="48" r="6"/><circle cx="80" cy="68" r="6"/><circle cx="60" cy="88" r="6"/><circle cx="100" cy="88" r="6"/></g></g>',
 chicken:'<path d="M45 88C24 48 69 40 87 62V39Q99 16 118 35L113 57Q135 100 97 112H66Z" fill="#f5d99f"/><path d="M98 31Q94 9 102 16Q111 5 116 26M115 45L136 52 115 58M64 110V123M90 113V126"/><circle cx="106" cy="41" r="3" fill="#181122" stroke="none"/>',
 coin:'<ellipse cx="84" cy="77" rx="43" ry="49" fill="#b57731"/><ellipse cx="76" cy="70" rx="43" ry="49" fill="#edc779"/><ellipse cx="76" cy="70" rx="33" ry="39"/><path d="M76 44L94 71 76 95 58 71Z" fill="#b57731"/>',
 hand:'<path d="M48 109L33 80Q27 63 37 62L54 79 48 34Q47 23 56 25L67 64 65 24Q65 12 74 17L80 63 85 28Q89 17 96 23L94 71 105 45Q112 35 118 43L108 94Q100 125 73 122Z" fill="#b690e8"/>',
 ticket:'<path d="M24 33H136V55Q116 70 136 85V110H24V85Q44 70 24 55Z" fill="#5f3f8c"/><path d="M51 37V107" stroke-dasharray="4 5"/><path d="M94 47L101 61 117 63 106 75 109 91 94 84 80 91 83 75 71 63 87 61Z" fill="#e8c17d"/>',
 slots:'<rect x="20" y="35" width="120" height="78" rx="13" fill="#4c2e70"/><path d="M58 38V110M101 38V110"/><g fill="#e7c078"><path d="M30 58H47L37 89H31L41 65H30Z"/><path d="M70 58H87L77 89H71L81 65H70Z"/><path d="M110 58H127L117 89H111L121 65H110Z"/></g><path d="M140 89H151V36"/><circle cx="151" cy="27" r="7" fill="#df8eff"/>',
 ball:'<circle cx="80" cy="72" r="47" fill="#f1e8ff"/><path d="M80 53L100 67 92 90H68L60 67Z" fill="#513471"/><path d="M80 53V25M100 67L126 58M92 90L108 111M68 90L52 111M60 67L34 58"/>',
 target:'<circle cx="80" cy="72" r="53" fill="#341e53"/><circle cx="80" cy="72" r="37" fill="#6a3fa1"/><circle cx="80" cy="72" r="19" fill="#af7ce4"/><path d="M80 72L130 24M113 43V22L137 11 136 35Z" fill="#eac98d"/>',
 bowling:'<path d="M55 41Q43 23 55 15Q67 9 71 24Q74 33 65 43L81 92Q84 115 57 117Q29 115 40 89Z" fill="#f7edff"/><path d="M54 44H68M52 51H70" stroke="#aa6cdf" stroke-width="6"/><circle cx="105" cy="95" r="32" fill="#7651a5"/><circle cx="99" cy="79" r="4"/><circle cx="112" cy="84" r="4"/><circle cx="99" cy="92" r="4"/>',
 balloon:'<ellipse cx="80" cy="57" rx="36" ry="43" fill="#ad6ce5"/><path d="M78 100L71 110H89L82 100M80 110Q105 133 72 137M59 40Q63 28 76 26"/>',
 case:'<path d="M25 57Q25 25 48 25H112Q135 25 135 57V114H25Z" fill="#50316d"/><path d="M25 61H135M45 28V112M115 28V112" stroke="#dfb678"/><rect x="69" y="51" width="22" height="28" rx="5" fill="#dfb678"/><circle cx="80" cy="62" r="3" fill="#301f44"/>',
 race:'<path d="M26 80L41 50H111L135 80V104H25Z" fill="#9c6adb"/><path d="M52 52L45 72H121L105 52Z" fill="#241a38"/><circle cx="47" cy="103" r="14" fill="#21172f"/><circle cx="115" cy="103" r="14" fill="#21172f"/><path d="M26 81H134M13 47H37M7 61H30"/>',
 pinball:'<rect x="35" y="15" width="90" height="116" rx="20" fill="#32204b"/><circle cx="65" cy="49" r="11" fill="#bb81ec"/><circle cx="96" cy="65" r="11" fill="#edc080"/><path d="M49 112L72 117M112 110L89 117" stroke-width="7"/><circle cx="60" cy="84" r="6" fill="#fff"/>',
 fish:'<path d="M110 71Q65 16 28 71Q67 126 110 71L139 42V100Z" fill="#81c3d6"/><path d="M64 43Q84 25 94 46M61 97Q86 116 98 90M69 52Q55 72 70 91"/><circle cx="47" cy="67" r="4" fill="#161321" stroke="none"/>',
 collection:'<rect x="25" y="26" width="44" height="49" rx="7" fill="#6c418b"/><rect x="80" y="26" width="44" height="49" rx="7" fill="#ae78ce"/><rect x="25" y="86" width="44" height="49" rx="7" fill="#dbb373"/><rect x="80" y="86" width="44" height="49" rx="7" fill="#6b9dbe"/><path d="M38 50L47 38 56 50 47 63ZM94 50L103 38 112 50 103 63Z" fill="#f3dcff"/>'
};
function svg(key,cls=''){return `<svg class="${cls}" viewBox="0 0 160 145" aria-hidden="true"><g stroke="#e6c5ff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">${shapes[key]||shapes.gem}</g></svg>`;}
return {svg};
})();
