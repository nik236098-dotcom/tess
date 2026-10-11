#!/usr/bin/env python3
"""Revision 2 of the beeline_integrated_io_15_91 package. Run on the EXTRACTED package.

    python3 fix_package_1591.py /path/to/extracted/package

Changes made in place (idempotent, refuses any other package):
1. test_beeline.py: the separate SUCCESS push is no longer cut to 4000 characters.
   It goes through the durable outbox (split into confirmed parts by the 15.91 sender);
   if the queue is unavailable it is sent directly, split, never truncated.
2. test_update.py: the preserved-handler hashes no longer depend on ast.dump(), whose
   text changed in Python 3.13; the installer's preflight failed on Python <= 3.12.
3. install.py: the reviewed package copies are installed after the input checksum
   matches, instead of re-applying edits.json line ranges.
4. test_beeline.py: the proxy login is removed from the code (TELEGRAM_DEFAULT_PROXY = "");
   the runtime already reads telegram_config.json "proxy" first. install.py refuses to
   run until that key exists, so Telegram traffic never silently loses the proxy.
5. test_beeline.py: autonomous SUCCESS/ERROR assist requests get a budget per page
   state (two per unchanged URL, then one per 30 minutes, none while the previous one
   is unanswered) instead of a full agent run and an identical report every 45 seconds.
6. test_beeline.py: registration/error policy. After the analysis report the runtime
   closes the error page, opens a fresh one and retries the row once; a second error on
   the same row skips it (logged, Telegram notice). A worker is never stopped by an error.
   The rule is also written into the DeepSeek system instructions and the task text.
7. test_beeline.py: a portal modal over the basket is dismissed (close button, Escape,
   pointer-events as a last resort) before the tariff buttons and the eSIM radio; the eSIM
   click falls back to force=True and a JS click; CDP page close gets 20 s and one retry.
8. test_beeline.py: the tariff card is found by its title (TARIFF_NAME) and «выбрать» is
   clicked inside it; the old "second button" rule picked the paid tariff after the site
   reordered the cards. The overlay dismisser leaves the dialog we need untouched.
9. test_beeline.py: the parent watchdog counts real page activity as ROW_START progress,
   long registration steps refresh the heartbeat, and the «изменить» retry happens in
   place before any basket reload.
10. test_beeline.py: the parent watchdog samples the CPU time of the worker process (and
   its child solver) from /proc while the protected matcher runs; a matcher still computing
   between stage reports is alive, a blocked or hung one burns no CPU and is caught by the
   unchanged 75 s rule. local_matcher.py is not touched.
11. manifest.json, edits.json, SHA256SUMS.txt, verification.json, test_results.txt are
   regenerated so every checksum the installer verifies is consistent again.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import re

MARKER = "SUCCESS_PUSH_DURABLE_1591R2"
PROXY_MARKER = "PROXY_FROM_CONFIG_1591R3"
EXPECTED_INPUT_OUTPUT_SHA = "9e216a70bb1e931c2e9568687c26564a0132bccd6b748dd42fef4eff9335fa50"
# test_beeline.py of the first build and of revision 2 are both accepted as input.
ACCEPTED_PACKAGE_SHAS = {EXPECTED_INPUT_OUTPUT_SHA,
                         "8f5fc960fc6cc44faebc19eae0709057f3c8c627d623d9219a0c85cff81d3012",
                         "437155a246d1e370a68cc29ec54850944837f0a575600c57c9f30b9849ebdf73",
                         "b835682314ab8958af4500f7176ca660608f14f09bb7bd02827eb503a23597b0",
                         "31cbd8b287f7c1deea89a669fabdcd14fab0bfee631b7ce87c5531493a05265a",
                         "14ada30d264a994bdb675655b495c662217298a6b0327e6ea98dce99e4675433",
                         "ec65b2fa802131dbd7f2e679f422c40ddae10cc842bff784869925e14b16c105",
                         "6023e5266b8317cd0051fbec7988d0f65e30c10f26fc95309d960ebf995997c9",
                         "6852517bf0eadb15f70359ac93b9c49632926cb3aef9f817c712ea099330248b",
                         "747c7f08c994baa104d82ebb5d3302215bc4f1147e238b66629bd5037710c47d",
                         "e0f5748ea3f7c19e6409a1e4f63fc9e00c322f8c38365134af0f13bf4bd8e14f",
                         "04e07acd1a019a943c72237a6c6c61b34134f7b753ce3f3b484c832ce742ae9d",
                         "21772a39422eeae8224f580beecad29171105885101b76f100190f6d64fd3e7c",
                         "1cc1769f3ec9bd04b325be73fed182a4a05f082339820682601c3bd4be7483f6",
                         "3bee3697775d818df6c1fe82c3096574f00a1c289aaf26c7a7e96d2f614b7597",
                         "1ba0e4f3af9dcc2fa8d78e5eee0033ec48489c402f4c49be9d4e799eb1a786ec",  # r17 output
                         "e8f5e036c2f33ab9d8f27a98deceb25356511cd253fc871f929c16d619f45d75",  # r18 output
                         "341513d5df545f6711f9c5f1e0de7d464d586b6c0afe4ac2fc019a27308457ec",  # r19 output
                         "bb57f0437e52c61d801e94020c3d72f9bbca2b2bbef09b63e0d746e5de9a59f2",  # r20 output
                         "90ddb7d43cfbb2d944a1fb23c62aed15cb3a9d3090810864402aa31b5410a1b0",  # r21 output
                         "fd1ed72b18db63993d0c288fa7ad8449e3e7827fa2b2697569dd79a9053ec3dc",  # r22 output
                         "10af519a75ce7a6813dae1b9b7bd95192cb81587e19361325f1e69e5a231269e",  # r23 output
                         "2e81b5bf57f5da86abec14e2b9bcd7961f44d3c87c54689819a2038a43533057",  # r24 output
                         "aac470f2ecd3e0d4d34b399860cda4393a0fa1896b24d206ea2c794558e853a2",  # r25 output
                         "72110535925a3167e91c621a29e2d46d090f7e76b03bb250df9f35530bdcaa5d",  # r26 output
                         "786a170bbe7f1861e225ec19f150c20ca176f5dbb55beeeb02924522cb29a6f3",  # r27 output
                         "6482ff2cfbc544f86587731e6d84a7ba5c9858987ca5700b60032d2ec4a905cf",  # r28 output
                         "e2c48c93641a62328a976b2197be2b3fba0ff0586819709eacc52afd27042e52",  # r29 output
                         "0b6cc34c63b6cfb1eb2f38909d41b05966eb1251b77c52cf1012d7cd4e95c3ab",  # r30 output (prompt only)
                         "bd07c22559bcd89c0244ed2e67e75c1ee1139274af0e627732b0444f58b546c8",  # r31 output
                         "f64ef74d8f4b6b3875c77253e23ede004065f6afcfc342e971c249138f570541",  # r32 lite output (FIX_1591_WITHOUT_R31=1)
                         "5a4c11e2d64d6d32bed1544d8f83ad44bfdb0c64b33f2df9eeda780d1db8b3dd",  # r32 output
                         "92c9cc68e5cfd3a0f8717d4bb53fb247e43f3564dc55dac75f2bd1b6924112f0",  # r33 lite output
                         "8561fef2069ee3c6df376c6060084aca717405e63f009d96bb0b98aa4aa7c1bc",  # r33 output
                         "abd23f11da908dd2e3bf17e7b5321a95505eb7fcf8eb7d41c8b9cb622c51322f",  # r34 lite output
                         "941b2964bf5f0b549047d4776ad830996951d8f6d35619e20dfed6763f4bc7e2",  # r34 output
                         "0544d1e2190d7ac7a2d091fe2370a558f038dbef17dbb775ce973d7a86642643",  # r35 lite output
                         "1a0258ca2f63186b153280b6e546652deebf624e426fdc629e7348560023c5a4",  # r35 output
                         "725adc5426e06707060bd25daa5af8fd4d66e83bfe064869f323177db3d8a12e",  # r36 lite output
                         "655faf868b4a4ace53dc7845617b4b765890d833822eb7c1d5b2d8b61fcbcb2f",  # r36 output
                         "cce2c689b26dd7ea0aa865576071d7b8372768efb7d67ec8dbb1ae23bf0c5738",  # r37 lite output
                         "a31f394aa9d9b708bb9c85c182a871dd0d63b96de78de58429c5746a07babd44",  # r37 output
                         "ef28ef77fbb8cb8afac35e6daaaeffee983e759322ebafb76c06e2d5fcdce6c1",  # r38 lite output
                         "74a466855054bb9f8cf05ae05c66224a519f0c1322ad695316006ae4aad40348",  # r38 output
                         "e37251fe2500cf89471a3e042f2d7a018c8b98748c933e15b965f1ae0333e00f",  # r39 lite output
                         "85d8693a6d059492252969da1f11966aa79c25fbe42c6ae6a3c6aacd7102c57a",  # r39 output
                         "df25464f90f9f73d006d821da6a918b94386631e30990f42524db157159b6e81",  # r40 lite output
                         "a2dd94165ec5926ad1512956706843987b7ca60efc4a91ec25e95a7de83eb604",  # r40 output
                         "500488cc68d96a1cebda5d421ca4ca653329494d798bd2225ce0ef4b330421ef",  # r41 lite output
                         "f05c32d36010b729259267d3f376cd44ae3a7feb12c653f36efee830e10ee8a6",  # r41 output
                         "596d521c36270a13b733832a75c694531910035ba624503e4e0cfd2533305fd9",  # r42 lite output
                         "a20d4ff24cf13165a2d75737a4caddea5a690057b42c9236d7ca242894ae2fc1",  # r42 output
                         "81c76b0265edeb7a0aa6d31abcd128754b03787ac7860ba45e3e9651929023a7",  # r43 lite output
                         "94226cc00b365c7fcf3d644d2fdf19f1f4a208c31ada602429325af7bab390b8",  # r43 output
                         "c6d5fda2950aee0bb11b3029cfbbed3fb040ee0602d35be103a9d09a251d106e",  # r43 exp8 output (FIX_1591_EXPERIMENT=browsers8, lite based)
                         "8f719b343e07cfdc2ab3d66f44b1786b368fe8300fabe923aaaa946c60ac4e6f",  # r44 lite output
                         "b018a08d19e835188a7db34ee666cd311813a4bf84c4ba4d0c328e5429d69409",  # r44 output
                         "0dfc1ad88d2c5adce03a4d86845e2332982da4090d7e4e0d2306036ab7649ed2",  # r44 exp8 output
                         "342653a2a33ecebaf2d8041a6b50e18803c9ba352422cba969b71d0f27ad9266",  # r45 lite output
                         "4b683ec4f6ca6a1d6eb4758f75e302331064e7930ea93f9247918956c7972d8d",  # r45 output
                         "9fab6235a28e8df26a93f71c13cd7f96b0a6d3483ff4c3285d72322dd9eec1cc",  # r45 exp8 output
                         "7275523887462f81983785d57e8acbbc37f88a4cc046ff22b12c490120d3add6",  # r46 lite output
                         "5eb56796a49d7555e6bf8eb8f644e2fb0dfc7468d211c91e26e355f65f4dead2",  # r46 output
                         "0190d63301cb9d8b3e1102902489813fd1a24ff4d3e270da8138dbd60e24c2dd",  # r46 exp8 output
                         "0a9170c05a703f46232345b1eb3ab8a31fd72438880f111e67753fd3ce38535e",  # r47 lite output
                         "7094978d4a2900df39257572619963c579909cfc3cc29259887b13b2d007b7fe",  # r47 output
                         "ee14eacc783114065a00649bdf1a78872ca74c00bbc936a2f0e01e7040638ff5",  # r47 exp8 output
                         "45925d827db3e587aa6d7d7b12888888b99d9f51799e14b88f258876db43b72b",  # r48 lite output
                         "3645c2db0ac230dae1201fb32d83826d4d95d638258d208d853a26ffa7348706",  # r48 output
                         "a9b7c58e581b6b0ecb19c4a9303ed94d253181dc56648660b0b93269d41cb293",  # r48 exp8 output
                         "a13c867e3dd9385c683a4ef1114ef7580d8767de4a555bf05764d705add4216d",  # r49 lite output
                         "c85853861d6522b598fc80f8afd85a98596ba22e2878447dab18dba17351f0d7",  # r49 output
                         "a23d36bbb0712b40a3bf86834458a5bd32187b0dac36fc55e19cc385084d59bb",  # r49 exp8 output
                         "0e096c8f8b07be0aa13685ca9390be67716ffe2da0f2afce8a2e48b9b9ccc84c",  # r50 lite output
                         "f47094fadff8d8b884b526453c6c696007b796e7128f81f80d56583262f4cd33",  # r50 output
                         "6c75c1fa45f918bc0bc00a97f0109e7f6f6fa609b57055b4e3d088824324de5e",  # r50 exp8 output
                         "2ed7d9c9460bc48883655306b22c9b6a48e724515ca48544d574bfaa10754d14",  # r51 lite output
                         "446432dd4e2761eb47123d967a25f9a89cc8160e512abf750e1b51cc3098ae2d",  # r51 output
                         "c22583a4e01233102cdb04ed6e6a7ba7228a7774705844c62e85376a85b6efc8",  # r51 exp8 output
                         "5eb2f6d56fdcde85f9f18b573e55735a3ad1c7767dc622d0cc3a012cda51bb25",  # r52 lite output
                         "93a30ea7eccbc66eaef0f1a0423f91193af3f01a515f28a7d11f36ac23b8c72f",  # r52 output
                         "ab50bf0d0987d25005f469ae606ee1ed91f9b7a9f81bfba26a6e5ba5aedcc8ef",  # r52 exp8 output
                         "01e027e9ef8c9bb9b50306e94c2a94904454afebb718f945a9cd1f8f9ef9ad2b",  # r53 lite output
                         "2c7e6633bcb373ad787d57944fdd9514bce121420d5173b3af41cafe570b5b99",  # r53 output
                         "9cda561640d602f6f96671ed08fe3fccdf48d79321d38927f991f25153105ae7",  # r53 exp8 output
                         "3e0b9e6fb9d42a3087c0bdd36390ada326297e6db5e929fc38237bffa87f0157",  # r54 lite output
                         "d85696cf3ec4ed306145280995a30aeea132ebc326f52f84c6610ae6290de499",  # r54 output
                         "c99e25aec5b4818b37bd63c76600738d7b4395167bc90d9bb3b5bded781084a3",  # r54 exp8 output
                         "3c774fb6f0987b24311f081c6a3eed057b888d9bf3cdc51fca9d80b96424f090",  # r55 lite output
                         "6645fa2454ff34c0a1d4f8d977490307d91a4cff8f9c7d745289cac41db3f151",  # r55 output
                         "1693ccaa9bbb671b5d7d1efd3c10a3826e3c2228674109c68e22a5fcf0a5d752",  # r55 exp8 output
                         "5e2e8e59ebd81dcc07c1f3bd8261a571306cec2df192e906ae41cee6ec050368",  # r56 lite output
                         "d583db4fc8115f85ed7ff71a7191597972d8749c79372b1489ab6b1d1f520583",  # r56 output
                         "09d64476b286c2e5abe00d108c75b1782a503069aec05c2c69b8e5e6ad062447",  # r56 exp8 output
                         "fb306c7114479fcbbdd42aa6353e8fde7c75c08f5b91a7d1b6092749a04d7e7b",  # r57 lite output
                         "d680e48b2bb236d504ac8b5ab9222307051e1b2de0416cbf066bb0d2c921a5ee",  # r57 output
                         "cd1d831520b17257409fde5abc0d3bcf773cdc7009a6b1b9990b8ff22da12f05",  # r57 exp8 output
                         "660185c602a07efeb3dceaf577f0c0c05524fe5d304c284d09b3d57502891faa",  # r58 lite output
                         "83efdd02f9a9ed2d80e22af45bab6264ad84c65e63adafe3a902fb2f0178abd0",  # r58 output
                         "fd8d77257aec208ff2a2a83fe8e8ba8a957db8b20f7b40636b97f1f8b59a0b45",  # r58 exp8 output
                         "aefb7f0bab3bec46cc8d8c5c67103f00ab0e5dde0042c76e6632fcb8ac8c992b",  # r59 lite output
                         "6ea77c42ead267a71db4256d950aa6b203ac78ccb0ab790e33b552aeb634bece",  # r59 output
                         "65d31f8ba6624c28f026a3dfb27ce968fd17d08349355b353b1a0b5d3826bc4e",  # r59 exp8 output
                         "34a5613c9f0e78425bf1b3e3df3fe961460a6025c719f38afd1f800a57fc1ada",  # r60 lite output
                         "0755fa96e5d5a14314a03e8b5e4a2b7719c0fbb537a7a9fe1d9ee17d939b0361",  # r60 output
                         "93d993ccde788d83ed11f037075de1dcd05bbcfd21094fa35ec1d501ac16f538",  # r60 exp8 output
                         "216c3226f11efe4ffddeebc3b025943d9b7e073597b69d21876cf8eb3535803a",  # r61 lite output
                         "f825f27874a025b8b47918a8ed78e6ee8183cc54c8e1c2171b098963934e538f",  # r61 output
                         "c33cdb04fe32344c93678a69e354fb7795d1d9acff1b34a7122e4e0ef4fcd7f4",  # r61 exp8 output
                         "995b045e6ecdf18c6cb8ffda39faf83114f78baab085d8af8897cdc91e861fba",  # r62 lite output
                         "dc8975d6c6c7fab9045d29f17e61bbfec099c4cefadb1187d967f529f4c02f4e",  # r62 output
                         "f54a72b3df9340bc1d1638d49088e8152b978c5394f06030883450811aa643b1",  # r62 exp8 output
                         "74aa6270f219a1cecc327f98f828f77327252a631bbe6aab57a406aaec6231a4",  # r63 lite (published by hand)
                         "a07b58b2410652947657d27bfb1a8e0ee3f4eeb0eef3122a3653e04a673998b2",  # r63 (published by hand)
                         "de45d56906a4e1a7377c293bc5ad59035d7cc863ffa73365595eb6f4d8171c7b",  # r64 lite output
                         "568d85096d121bf2bf5d972811654f2305aebe2a6e73bfac22703d0099529fb4",  # r64 output
                         "ea4aaaa8157252598256a9bd397970456eb7a349ecd09abc491e05826427a0d6",  # r64 exp8 output
                         "516921257f41362a6179514e22b29e4ca2be3b3d889fc8a5f64f8daad4516247",  # r65 lite output
                         "c9b8c5f977cf171e809668cee372f1d1a29819ab84a85c8ff7441891ac672770",  # r65 output
                         "31af9d9eceeb010627922c94a228fe2ce4df4d0091251a9301763822aded203a",  # r65 exp8 output
                         "2acb9788c8ca15faf5964b156551a64aa5d52302fb139547b699914902c00e7c",  # r66 lite output
                         "32176b20666a07c335720ba68ec72bfd12ca004509e24333386c49bc4deff50a",  # r66 output
                         "f8d6f305e207cc35d2ef37215d76c5fa904642bc82ce8270c891dc28af0a6568",  # r66 exp8 output
                         "b79bcf1cc7579eb2ca0e8333e272f1f2b7ab06bbba6eade5098898ee7669e6a4",  # r67 lite output
                         "5d0345183cbcdee10bdebc33830b1c33b8977dd5dca28f0447ce68fa993fa6fe",  # r67 output
                         "b7dd73283a0dd995a96f3514b4c658bcb91ffadcb68203b36a7d26db5befcb00",  # r67 exp8 output
                         "9cbba2a5ecb649cac3969cb2f8bf67ce2679de13f3a92002c0a022aac95022d5",  # r68 lite output
                         "6d4055e86fb85f589c27c11f3bfdb8bb848c417d53bdae8e23705f80edfefc9c",  # r68 output
                         "02aba622b3f2867f6a8d19a57b1d257463b9ab3c95efe016768075bddf8d7992",  # r68 exp8 output
                         "fa0e97c5da8a9369b31c65146922e2d61a59660184f50fa6110647f90095dc2b",  # r69 lite output
                         "b18a6cd0914baad00f3301d2bef4979e9d01813682a3af738dedfce2626d7a34",  # r69 output
                         "ea0511ec3650b830d75c40dfad187698bfbd09447acfaf26ff65101ad838b29c",  # r69 exp8 output
                         "679c881a19b388da8523eba3094b249f3c22d884a71aeca05f9a69e0886d4901",  # r70 lite output
                         "c9c55e40b616e577b735243cf72c347a806a0630f38a4044e49fa2b7348ba255",  # r70 output
                         "f5055f9bcadadcb55dc1019bad40608a58247ff86381cbf853495d1c99e85ab6",  # r70 exp8 output
                         "7226d133e2918fd9127106c0455e094fb06eb7adfef7e6c53079e42782a788b9",  # r71 lite output
                         "e65e08e87bc4a7bf05f5c262234cfd7c0efc6ca8a70430d7b490e7de45284be0",  # r71 output
                         "4b3d105bcde5864be01443483168c909060cd16a0e94a30e9ea46217750c81f7",  # r71 exp8 output
                         "777bbc275abd0c14e3735d78ea14de4b257bd5f3141e9ac69acb5cbcb627fdac",  # r72 lite output
                         "d00e998c078403f48e7f6ce6b50240672b7bfe36a397e76350540008a582e618",  # r72 output
                         "40dc8d6e912567016f6a390d66a11913841ead368f908d92e242d024e95da7eb",  # r72 exp8 output
                         "37477773fc6087f21bd16aeaf763ff53f6e73bc9bb3550efa491bd3b11c60e89",  # r73 lite output
                         "f8cc737b46040e699572360e6a745be075a46d127a99ca689412f2535f7373c9",  # r73 output
                         "6b27b6701c6aa342b9c477c0df344f857c1157b8e76dbbc5344160f01318ee55",  # r73 exp8 output
                         "c98b0659205e3f5d6d6f986f1f2faa1d267d201f213cb01614023074aa936f59",  # r74 lite output
                         "86d2cda219e4f5b1fec2d5b6720f7150101a8bbff6c5057517f219931579df3d",  # r74 output
                         "294d5c8016c2c76f3ead4b2d1eb1a3966fc64c4bb7e984119f1a090624e8e27a",  # r74 exp8 output
                         "d3b229693f7792e04510a3c19b3ee48e1820746f0cb83ffb1837e58b022b181b",  # r75 lite output
                         "3e3856f05f853c584feabb54fbead378a91cfa49c4ae2649e5864084abfe6919",  # r75 output
                         "d37437eb4d1446975fa5748011f617e4b648ce99278eaf185d97c9524cd7f9d1",  # r75 exp8 output
                         "d6c58c0b7522bff2621e70133e94664bb3c3f4762d6b4273344df3de14308d4a",  # r76 lite output
                         "3e2097a0fe748293bbb92f3250ca56318be1de6e45765b9d1ab4e56b250cdbfa",  # r76 output
                         "6a63c7994939fe5ca3c873646696a7fc70a05f17f339020b10532a21ba9000e0"}  # r76 exp8 output

# Revision 5: registration/error policy. After the detailed analysis and its report the
# runtime closes the error page, opens a fresh one and retries the row once; a second
# error on the same row skips it. A worker slot is never stopped because of an error.
ERROR_MARKER = "ERROR_RECOVERY_1591R5"

# Revision 6: a portal modal (role="dialog" aria-modal="true", "подбор номера") started to
# cover the basket page. Playwright clicks on the eSIM radio and the tariff buttons were
# intercepted, every attempt failed and the row looped through same-row restarts forever.
OVERLAY_MARKER = "OVERLAY_DISMISS_1591R6"

# Revision 7: the tariff card was chosen by position (second «выбрать»); the site reordered
# the cards. The card is now found by its title. The overlay dismisser leaves a dialog alone
# when it contains what is about to be clicked (the tariff picker is itself a modal).
TARIFF_MARKER = "TARIFF_BY_NAME_1591R7"

# Revision 8: the parent watchdog judged ROW_START by the last phase publish only, so a
# row busy with real page loading for 120 s was "stalled" and recovered mid-action; the
# «изменить» retry reloaded the basket (losing its state) before trying again in place.
ROWSTART_MARKER = "ROW_START_ACTIVITY_1591R8"
ROW_PROGRESS_HELPER_R8 = '''# ROW_START_ACTIVITY_1591R8
def _row_progress(page, note):
    """Refresh the worker heartbeat from inside a long registration step."""
    publisher = getattr(page, "_publish_worker_phase", None)
    if publisher is None:
        return
    try:
        publisher("ROW_START", note)
    except Exception:
        pass


'''
OLD_WATCHDOG_ROW_START = '''        if phase == "ROW_START":
            if logical_age >= ROW_START_STALL_SECONDS:
                stalled.append((tab_id, proc, info, logical_age))
            continue
'''
NEW_WATCHDOG_ROW_START = '''        if phase == "ROW_START":
            # ROW_START_ACTIVITY_1591R8: real page activity (requests, navigation) is
            # progress too; only a row that is silent on BOTH clocks is stalled.
            activity_age = now - float(info.get("activity_time") or info.get("time") or now)
            if min(logical_age, activity_age) >= ROW_START_STALL_SECONDS:
                stalled.append((tab_id, proc, info, min(logical_age, activity_age)))
            continue
'''
OLD_TARIFF_OPEN = '''        print("Открываю выбор тарифа...")
'''
NEW_TARIFF_OPEN = '''        _row_progress(page, "открываю выбор тарифа")  # ROW_START_ACTIVITY_1591R8
        print("Открываю выбор тарифа...")
'''
OLD_TARIFF_RETRY = '''        except (PlaywrightTimeoutError, AssertionError):
            diagnostic.snapshot("tariff_change_button_not_ready")
            print("Кнопка «изменить» не найдена с первой попытки. Обновляю только эту вкладку...", flush=True)
            page.reload(wait_until="domcontentloaded", timeout=60000)
            click_tariff_change()
'''
NEW_TARIFF_RETRY = '''        except (PlaywrightTimeoutError, AssertionError):
            diagnostic.snapshot("tariff_change_button_not_ready")
            # ROW_START_ACTIVITY_1591R8: a reload resets the basket; retry in place first.
            print("Кнопка «изменить» не нажалась с первой попытки. Повторяю без перезагрузки...", flush=True)
            _row_progress(page, "повтор «изменить» без перезагрузки")
            page.wait_for_timeout(3000)
            try:
                click_tariff_change()
            except (PlaywrightTimeoutError, AssertionError):
                print("Кнопка «изменить» не нажалась повторно. Обновляю только эту вкладку...", flush=True)
                page.reload(wait_until="domcontentloaded", timeout=60000)
                click_tariff_change()
'''
OLD_CHOOSE_PRINT = '''        print("Нажимаю вторую кнопку «выбрать», как в записи...")
'''
NEW_CHOOSE_PRINT = '''        _row_progress(page, "нажимаю «выбрать» в карточке тарифа")  # ROW_START_ACTIVITY_1591R8
        print("Нажимаю «выбрать» в карточке тарифа...")
'''
OLD_ESIM_CALL = '''        select_esim(page)
        field = page.get_by_placeholder("+7 999 999 99")
'''
NEW_ESIM_CALL = '''        _row_progress(page, "выбор eSIM")  # ROW_START_ACTIVITY_1591R8
        select_esim(page)
        field = page.get_by_placeholder("+7 999 999 99")
'''
README_NOTE_R8 = '''

РЕВИЗИЯ 8 (fix_package_1591.py)
Watchdog и ROW_START. Родительский watchdog считал «нет прогресса» только по времени
последней публикации фазы, поэтому строка, которая 120 секунд реально грузила страницы
корзины и тарифа, признавалась зависшей и «восстанавливалась» посреди работы. Теперь
учитывается и реальная активность страницы (запросы, навигация), а длинные шаги
(открытие выбора тарифа, «выбрать», eSIM) сами обновляют heartbeat. Повтор клика по
«изменить» сначала выполняется на месте, без reload корзины; reload остаётся крайним
средством. Маркер: ROW_START_ACTIVITY_1591R8. Изменены parent_watchdog и run_registration.
'''

# Revision 9: the protected matcher reports progress only at stage boundaries, so a solving
# step longer than 75 s looked like a stall and the protected page was closed mid-check.
# The limit stays; the parent now samples the worker's CPU time (plus children) from /proc:
# growing CPU = computing = alive, flat CPU = blocked/hung = silent, the 75 s rule applies.
MATCHER_MARKER = "MATCHER_HEARTBEAT_1591R9"
MATCHER_HELPER_R9 = '''# MATCHER_HEARTBEAT_1591R9
MATCHER_CPU_MIN_RATIO = 0.05  # share of one CPU below which the matcher is not computing
_MATCHER_CPU_STATE = {}


def _process_tree_cpu_seconds(pid):
    \"\"\"CPU time of a process plus its live children (a native solver may be a child).\"\"\"
    try:
        ticks = os.sysconf("SC_CLK_TCK")
    except (AttributeError, ValueError, OSError):
        ticks = 100
    total = 0.0
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "r") as f:
                fields = f.read().rsplit(")", 1)[1].split()
            if int(entry) == int(pid) or int(fields[1]) == int(pid):
                total += (int(fields[11]) + int(fields[12])) / ticks
        except (OSError, IndexError, ValueError):
            continue
    return total


def _matcher_cpu_age(proc, now):
    \"\"\"Seconds since the worker process (or its child solver) was last seen computing.

    Sampled by the parent between watchdog runs. A matcher busy with SHAPE/MATCH work
    keeps this near zero without any stage report; a matcher blocked on the page, a lock
    or the network burns no CPU, so this grows and the 75-second rule applies as before.
    \"\"\"
    pid = getattr(proc, "pid", None)
    if not pid:
        return float("inf")
    cpu = _process_tree_cpu_seconds(pid)
    if cpu is None:
        return float("inf")
    state = _MATCHER_CPU_STATE.get(pid)
    if state is None:
        _MATCHER_CPU_STATE[pid] = {"cpu": cpu, "time": now, "progress_at": now}
        return 0.0
    wall = now - state["time"]
    if wall > 0 and (cpu - state["cpu"]) / wall >= MATCHER_CPU_MIN_RATIO:
        state["progress_at"] = now
    state["cpu"], state["time"] = cpu, now
    return now - state["progress_at"]


'''
OLD_WATCHDOG_MATCHER = '''            if matcher_age >= PROTECTED_MATCHER_STALL_SECONDS:
                stalled.append((tab_id, proc, info, matcher_age))
            continue
'''
NEW_WATCHDOG_MATCHER = '''            # MATCHER_HEARTBEAT_1591R9: a matcher still computing (the worker process or
            # its child solver keeps consuming CPU) is alive between stage reports; a
            # blocked or hung matcher burns no CPU and is caught by the same 75 s rule.
            matcher_age = min(matcher_age, _matcher_cpu_age(proc, now))
            if matcher_age >= PROTECTED_MATCHER_STALL_SECONDS:
                stalled.append((tab_id, proc, info, matcher_age))
            continue
'''
OLD_HEALTH_MATCHER = '''            matcher_age = now - float(
                (info or {}).get("matcher_time")
                or (info or {}).get("time")
                or now
            )
            return phase, logical_age, matcher_age, bool(proc and proc.is_alive())
'''
NEW_HEALTH_MATCHER = '''            matcher_age = now - float(
                (info or {}).get("matcher_time")
                or (info or {}).get("time")
                or now
            )
            if phase == "PROTECTED_CHECK" and proc is not None:
                matcher_age = min(matcher_age, _matcher_cpu_age(proc, now))  # MATCHER_HEARTBEAT_1591R9
            return phase, logical_age, matcher_age, bool(proc and proc.is_alive())
'''
README_NOTE_R9 = '''

РЕВИЗИЯ 9 (fix_package_1591.py)
Heartbeat матчера. Матчер сообщает о прогрессе только на границах этапов (CAPTURE, SPLIT,
MATCH, SUBMIT, SHAPE_NATIVE…), поэтому этап дольше 75 секунд выглядел как зависание, и
защищённая вкладка закрывалась посреди проверки. Лимит 75 секунд не менялся: исправлен
сигнал. Родительский watchdog читает из /proc процессорное время процесса worker (и его
дочернего решателя, если есть): пока оно растёт, матчер считает, и «возраст» матчера
обнуляется; заблокированный или зависший матчер CPU не расходует, поэтому замолкает и
ловится правилом 75 секунд как раньше. Замер идёт в родительском процессе, GIL worker'а
ему не мешает. То же правило применено к проверке «unhealthy» для действий DeepSeek.
Маркер: MATCHER_HEARTBEAT_1591R9. Изменены parent_watchdog и _host_worker_health (в main);
local_matcher.py не трогается.
'''

# Revision 10: the matcher computes the same scores faster. symbol_matching.py 14.0 from the
# server is replaced by 14.1 (matcher_r10/symbol_matching.py): identical thresholds, descriptors,
# rotation steps and assignment logic; shape_costs compares one rotated candidate with all
# references through matrix products, thin() looks the Zhang-Suen decision up in a table over
# the mask's bounding box, each mask is thinned once, the NATIVE and CLEAN passes share one
# rotation sweep, identical threshold masks reuse regions(). local_matcher.py is untouched.
MATCHER_SPEED_MARKER = "MATCHER_SPEED_1591R10"
SYMBOL_MATCHING_SOURCE = Path(__file__).resolve().parent / "matcher_r10" / "symbol_matching.py"
SYMBOL_MATCHING_REFERENCE = Path(__file__).resolve().parent / "matcher_r10" / "symbol_matching_14_0_reference.py"
# sha256 of the server's symbol_matching.py (MATCHER_VERSION 14.0), the only accepted input.
SYMBOL_MATCHING_INPUT_SHA = "915368d66804f64d4d7d7de42d2e474f1ea29ffe5b14c352b67d054ee40c8c35"
OLD_INSTALL_FILES = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py')\n"
NEW_INSTALL_FILES = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py', 'symbol_matching.py')\n"
OLD_INSTALL_LOOP = "    for name in ('test_beeline.py', 'server_controller.py'):\n        path = app/name\n"
NEW_INSTALL_LOOP = "    for name in ('test_beeline.py', 'server_controller.py', 'symbol_matching.py'):\n        path = app/name\n"
OLD_INSTALL_IMPORT = "'import test_beeline as a; import server_controller as c; '\n"
NEW_INSTALL_IMPORT = "'import test_beeline as a; import server_controller as c; import symbol_matching as s; '\n"
OLD_INSTALL_ASSERT = "'assert a._io1591.VERSION == \"15.91-io\"; print(\"IMPORT OK\")'"
NEW_INSTALL_ASSERT = "'assert a._io1591.VERSION == \"15.91-io\"; assert s.MATCHER_VERSION == \"14.1\"; print(\"IMPORT OK\")'"
OLD_TEST_FIXTURE = ("        self.old={'test_beeline.py':b'old app','server_controller.py':b'old controller'}\n"
                    "        self.new=dict(self.old,**{'test_beeline.py':b'new app','server_controller.py':b'new controller',"
                    "'operator_runtime_io.py':b'helper'})\n")
NEW_TEST_FIXTURE = ("        self.old={'test_beeline.py':b'old app','server_controller.py':b'old controller',"
                    "'symbol_matching.py':b'old matcher'}\n"
                    "        self.new=dict(self.old,**{'test_beeline.py':b'new app','server_controller.py':b'new controller',"
                    "'operator_runtime_io.py':b'helper','symbol_matching.py':b'new matcher'})\n")
OLD_TEST_COMPILE_LIST = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py'):"
NEW_TEST_COMPILE_LIST = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py','symbol_matching.py'):"
# Revision 11: the DeepSeek lanes hang in page.evaluate (no timeout in Playwright) when a
# worker tab stops answering; the lane stays in busy_browser and the supervisor never restarts
# it, so Telegram goes silent until the service is restarted. The page collector now runs in
# its own thread with a deadline; on overrun the lane process exits and the parent respawns
# it (releasing its inbox claims). The supervisor also restarts a lane stuck in busy_* beyond
# a hard ceiling.
OBSERVER_MARKER = "OBSERVER_TIMEOUT_1591R11"
OLD_COLLECT_DEF = ('def _observer_collect_pages(cdp_urls, with_screenshots=True):\n'
                   '    """Connects read-only to both Chromium instances and snapshots worker pages."""\n')
NEW_COLLECT_DEF = ('def _observer_collect_pages_unbounded(cdp_urls, with_screenshots=True):\n'
                   '    """Connects read-only to both Chromium instances and snapshots worker pages.\n'
                   '\n'
                   '    Unbounded: call _observer_collect_pages, which adds the deadline.\n'
                   '    """\n')
OBSERVER_HELPER_R11 = '''# OBSERVER_TIMEOUT_1591R11
OBSERVER_COLLECT_TIMEOUT_SECONDS = 45
AI_LANE_BUSY_CEILING_SECONDS = 900


def _observer_collect_pages(cdp_urls, with_screenshots=True, timeout=None):
    """Bounded page collection for the DeepSeek lanes.

    page.evaluate has no timeout in Playwright: on a page that stopped answering (a tab
    being replaced, a hung renderer) it never returns, the lane stays in busy_browser and
    the supervisor leaves it alone. The unbounded collector therefore runs in its own
    thread with its own Playwright instance; if it exceeds the deadline the lane process
    exits and the parent respawns it, releasing its inbox claims.
    """
    import threading
    limit = float(OBSERVER_COLLECT_TIMEOUT_SECONDS if timeout is None else timeout)
    outcome = {}

    def run():
        try:
            outcome["pages"] = _observer_collect_pages_unbounded(cdp_urls, with_screenshots=with_screenshots)
        except BaseException as exc:  # re-raised in the caller
            outcome["error"] = exc

    worker = threading.Thread(target=run, name="observer-collect-1591", daemon=True)
    worker.start()
    worker.join(limit)
    if worker.is_alive():
        print(
            f"[AI] Сбор страниц не завершился за {limit:.0f} с (evaluate завис на неотвечающей "
            "вкладке) — процесс наблюдателя завершается, родитель перезапустит его.",
            flush=True,
        )
        os._exit(3)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("pages", [])


'''
OLD_LANE_STALE = '''            stale = (
                not state.startswith("busy_")
                and (now - last) > idle_limit
            )
'''
NEW_LANE_STALE = '''            # OBSERVER_TIMEOUT_1591R11: a lane stuck in busy_* beyond the hard ceiling is
            # restarted as well; a hung evaluate never comes back on its own.
            stale = (
                (not state.startswith("busy_") and (now - last) > idle_limit)
                or (state.startswith("busy_") and (now - last) > AI_LANE_BUSY_CEILING_SECONDS)
            )
'''
README_NOTE_R11 = '''

РЕВИЗИЯ 11 (fix_package_1591.py)
Молчание DeepSeek до перезапуска. Линии FAST и DEV каждые 5 секунд собирают список
worker-страниц через CDP и ставят на них телеметрию вызовом page.evaluate. У этого вызова в
Playwright нет таймаута: если вкладка перестала отвечать (например, закрывается при
восстановлении), вызов не возвращается никогда, линия остаётся в состоянии busy_browser, а
супервизор такие линии не перезапускает. Сообщения копятся в очереди без claim до перезапуска
службы, после которого разбираются все разом. Теперь сбор страниц идёт в отдельном потоке с
дедлайном 45 секунд; при превышении процесс линии завершается, родитель перезапускает его и
возвращает его сообщения в очередь. Супервизор дополнительно перезапускает линию, которая
дольше 15 минут находится в любом состоянии busy_* (агент разработчика обновляет состояние на
каждом раунде, поэтому легитимная работа под потолок не попадает).
Маркер: OBSERVER_TIMEOUT_1591R11. Изменены _observer_collect_pages и _ensure_ai_lane_alive (в main).
'''
# Revision 12: on the contract/signature screen the name, gender and birth date are plain
# text, not form fields, so capture_contract_details/final_profile_capture_v1583 (which read
# input/select/textarea values only) leave them empty in the SUCCESS record. A text capture
# reads "label: value" pairs from the page and its frames, validates each value by type,
# never overwrites captured values and dumps the page text once per worker for diagnostics.
PROFILE_MARKER = "SUCCESS_PROFILE_TEXT_1591R12"
OLD_CAPTURE_WRAPPER = '''_capture_contract_details_before_v1583 = capture_contract_details
def capture_contract_details(page, worker):
    result = _capture_contract_details_before_v1583(page, worker)
    try:
        final_profile_capture_v1583(page, worker)
    except Exception:
        pass
    return worker.get("success_profile") or result
'''
NEW_CAPTURE_WRAPPER = '''_capture_contract_details_before_v1583 = capture_contract_details
def capture_contract_details(page, worker):
    result = _capture_contract_details_before_v1583(page, worker)
    try:
        final_profile_capture_v1583(page, worker)
    except Exception:
        pass
    try:
        capture_success_profile_text_1591r12(page, worker)  # SUCCESS_PROFILE_TEXT_1591R12
    except Exception:
        pass
    return worker.get("success_profile") or result
'''
PROFILE_TEXT_HELPER_R12 = r'''# SUCCESS_PROFILE_TEXT_1591R12
# The contract screen shows the name, gender and birth date as plain text, not as form
# fields, so the input-based captures above leave them empty. This capture reads
# "label: value" pairs from the page text (main frame and iframes), validates every
# value by type and never overwrites a value that is already captured.
_PROFILE_TEXT_LABELS_1591R12 = {
    "full_name": ("фио", "фамилия имя отчество", "ф и о", "fullname", "full name"),
    "gender": ("пол", "gender"),
    "birth_date": ("дата рождения", "birth date", "birthdate"),
    "passport_series": ("серия паспорта", "серия"),
    "passport_number": ("номер паспорта",),
    "passport_issue_date": ("дата выдачи",),
    "passport_issued_by": ("кем выдан",),
    "country": ("страна",),
    "region": ("область", "регион"),
    "district": ("район",),
    "locality": ("населенный пункт", "город", "г."),
    "street": ("улица", "ул."),
    "house": ("дом", "номер дома", "д."),
    "building": ("корпус", "строение", "корп."),
    "apartment": ("квартира", "кв."),
}
_DATE_RE_1591R12 = re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
_FIO_RE_1591R12 = re.compile(
    r"^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}(\s+[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}){1,3}$"
)
_GENDER_RE_1591R12 = re.compile(r"^(мужской|женский|муж|жен|м|ж|male|female)$", re.I)
_PROFILE_TEXT_VALUE_RE_1591R12 = {
    "passport_series": re.compile(r"^\d{2}\s?\d{2}$"),
    "passport_number": re.compile(r"^\d{6}$"),
    "house": re.compile(r"^\d{1,4}[а-яa-z]?(\s*/\s*\d{1,3})?$", re.I),
    "building": re.compile(r"^[\dа-яa-z\-]{1,6}$", re.I),
    "apartment": re.compile(r"^\d{1,5}[а-яa-z]?$", re.I),
}


def _text_label_key_1591r12(label):
    """Profile key for a visible label, or None. Labels are matched whole (or as the first
    word of a longer label), so «номер договора» or «домашний телефон» never match."""
    hay = _norm_label(label).strip(" :;-–—\t.,")
    if not hay or len(hay) > 40:
        return None
    for key, words in _PROFILE_TEXT_LABELS_1591R12.items():
        for word in words:
            word = _norm_label(word)
            if hay == word or hay.startswith(word + " "):
                return key
    return None


def _text_value_ok_1591r12(key, value):
    value = str(value or "").strip().strip(":;,")
    if not value or value in ("—", "-", "–") or len(value) > 160:
        return False
    if key == "full_name":
        return bool(_FIO_RE_1591R12.match(value))
    if key == "gender":
        return bool(_GENDER_RE_1591R12.match(value))
    if key in ("birth_date", "passport_issue_date"):
        return bool(_DATE_RE_1591R12.search(value))
    pattern = _PROFILE_TEXT_VALUE_RE_1591R12.get(key)
    return bool(pattern.match(value)) if pattern else True


_PROFILE_TEXT_JS_1591R12 = r"""
() => {
  const vis = el => {
    try {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    } catch (_) { return false; }
  };
  const txt = el => ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  const pairs = [];
  const seen = new Set();
  const push = (label, value) => {
    label = String(label || '').replace(/\s+/g, ' ').trim().replace(/[:：]\s*$/, '');
    value = String(value || '').replace(/\s+/g, ' ').trim()
      .replace(/^[:：\-–—]\s*/, '').replace(/[;,]\s*$/, '');
    if (!label || !value || label.length > 40 || value.length > 160) return;
    if (value === label) return;
    const k = label + '|' + value;
    if (seen.has(k)) return;
    seen.add(k);
    pairs.push({label: label, value: value});
  };
  const containers = 'tr,dl,li,p,div,section,article,fieldset';
  document.querySelectorAll(
    'dt,th,[class*="label"],[class*="Label"],[class*="title"],[class*="name"]'
  ).forEach(el => {
    if (!vis(el)) return;
    const label = txt(el);
    if (!label || label.length > 40) return;
    let value = '';
    const sib = el.nextElementSibling;
    if (sib && vis(sib)) value = txt(sib);
    if (!value) {
      const row = el.closest(containers);
      if (row) {
        const t = txt(row);
        const i = t.indexOf(label);
        if (i >= 0) value = t.slice(i + label.length);
      }
    }
    push(label, value);
  });
  document.querySelectorAll('span,div,li,p,strong,b,em,small,a,label,dd,td').forEach(el => {
    if (!vis(el) || (el.children && el.children.length)) return;
    const t = txt(el);
    if (!t || t.length > 140) return;
    const m = t.match(/^([^:：]{2,40})[:：]\s*(.+)$/);
    if (m) push(m[1], m[2]);
  });
  let text = '';
  try { text = (document.body && (document.body.innerText || '')) || ''; } catch (_) {}
  return {pairs: pairs, text: text.slice(0, 20000)};
}
"""


def capture_success_profile_text_1591r12(page, worker):
    """Fill missing profile fields from the visible text of the contract screen."""
    targets, collected, texts = [], [], []
    if page is not None:
        targets.append(page)
        try:
            for frame in page.frames:
                if frame not in targets:
                    targets.append(frame)
        except Exception:
            pass
    for target in targets:
        try:
            data = target.evaluate(_PROFILE_TEXT_JS_1591R12)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for item in data.get("pairs") or []:
            if isinstance(item, dict):
                collected.append((item.get("label"), item.get("value")))
        if data.get("text"):
            texts.append(str(data.get("text")))

    profile = dict(worker.get("success_profile") or {})

    def put(key, value):
        if not key or profile.get(key):
            return
        if _text_value_ok_1591r12(key, value):
            profile[key] = str(value).strip().strip(":;,")

    for label, value in collected:
        put(_text_label_key_1591r12(label), value)

    for text in texts:
        lines = [line.strip() for line in re.split(r"[\r\n]+", text)]
        for index, line in enumerate(lines):
            if not line:
                continue
            match = re.match(r"^([^:：]{2,40})[:：]\s*(.+)$", line)
            if match:
                put(_text_label_key_1591r12(match.group(1)), match.group(2))
            elif _text_label_key_1591r12(line) and index + 1 < len(lines):
                following = lines[index + 1]
                if following and not _text_label_key_1591r12(following):
                    put(_text_label_key_1591r12(line), following)

    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    try:
        diagnostic = worker.get("diagnostic")
        if diagnostic and texts and not worker.get("success_text_dump_done"):
            worker["success_text_dump_done"] = True
            diagnostic.write("success_page_text_v1591r12", url=str(getattr(page, "url", "") or ""),
                             text="\n".join(texts)[:20000])
    except Exception:
        pass
    return profile


'''
README_NOTE_R12 = '''

РЕВИЗИЯ 12 (fix_package_1591.py)
Неполный профиль в SUCCESS-сообщении. На экране договора ФИО, пол и дата рождения показаны
обычным текстом, а не полями формы, а оба существующих захвата (capture_contract_details и
final_profile_capture_v1583) читают только value у input/select/textarea, поэтому эти поля
оставались пустыми. Добавлен текстовый захват capture_success_profile_text_1591r12: читает
пары «подпись: значение» из DOM и текста страницы, включая iframe; подписи сопоставляются
целиком («номер договора» или «домашний телефон» не принимаются за номер паспорта и дом);
каждое значение проверяется по типу (ФИО 2–4 слова с заглавных, пол, даты, серия 4 цифры,
номер 6 цифр, дом/корпус/квартира короткие); уже считанные значения не перезаписываются.
Вызывается из той же обёртки capture_contract_details, то есть во всех прежних точках
(post-auth review, sign-wait, finalize_success). Один раз на worker текст страницы
сохраняется в diagnostics (success_page_text_v1591r12) для проверки на реальном договоре.
Маркер: SUCCESS_PROFILE_TEXT_1591R12.
'''
# Revision 13: scheduled graceful restart. Every N minutes (Telegram: /restart 20m, /restart off,
# /restart now, /restart) the runtime enters a drain: each worker finishes its current row to the
# end (confirmation cycle, signing, DeepSeek assist included) and does not take a new one; when
# no worker is left the runtime exits with RESTART_EXIT_CODE and the controller relaunches it.
RESTART_MARKER = "SCHEDULED_RESTART_1591R13"
CONTROLLER_OUTPUT_SHA_R12 = "506a84c41558332c75cbf55abc8e940520a589b3bc754a6845ca1dd7515740e8"
# server_controller.py as produced by revisions 13..20 (unchanged between them); a server on any
# of those must be accepted by the installer now that r21 changed the controller again.
CONTROLLER_OUTPUT_SHA_R13_R20 = "5104af2bf68452b1dcd3b814b35e696699232087b92db87ee7e1e9a6ee1a8bd9"
CONTROLLER_OUTPUT_SHA_R27_R35 = "384e2c06274159c01dae2b9dc8698dff2a93912e5a6bf3de9eb57efce6d256c4"  # controller of r27..r35
CONTROLLER_OUTPUT_SHA_R36_R37 = "f3b36badf1e9d77a1dda6fe287b5210372d42a1846f993a28cf9c1f6aa7abacd"  # controller of r36..r37 (/res)
CONTROLLER_ACCEPTED_SHAS = {CONTROLLER_OUTPUT_SHA_R12, CONTROLLER_OUTPUT_SHA_R13_R20, CONTROLLER_OUTPUT_SHA_R27_R35,
                            CONTROLLER_OUTPUT_SHA_R36_R37,
                            "d561621ddacaa0c4e602a5da75842207a9b76f563f2d26202e75e9e7eeb6012b",  # controller of r38..r45 (menu)
                            "c700c997e758c55001e598e10b0386cd009bc7def04b89ee234aacda704484cd",  # controller of r46..r47 (/op)
                            "b008baad1551e6574389743c1b2810a39f03e198a5af4c3a823fe4296386c25c",  # controller of r48..r49 (BEELINE_AI)
                            "738c0f281ac6e59b6b0a62f07fc27217a73e817b45ceb9b93e1e681c00e21a4b",  # controller of r50..r51 (/clear)
                            "ab1c4088f714471f480dbe29af0e2359ad189850e386d2f53058082acf4162ae",  # controller of r52..r59
                            "6ba64b644e27ee202971a72d24b5efcfa9e5dfd7b1ce97515a17414f4b60f442",  # controller of r60 (menu hooks)
                            "989606fee80a565e000e1a5f45de01584e955a751ec639e7ce59dcff68d9ce85",  # controller of r63 (by hand)
                            "acfd905f16ef07a50d68e1017ff163c215119dfd5cd27f32929dbe516c22110e",  # controller of r64 (base tools)
                            "8a827f68aa4972f1c9ed1aeeec5f0de4b918dbb6e8bb1a4884f9abec2dd19935"}  # controller of r69 (one birth date)
RESTART_HELPER_R13 = '''# SCHEDULED_RESTART_1591R13
RESTART_POLICY_FILE_NAME = "restart_policy.json"
RESTART_DRAIN_FILE_NAME = "restart_drain.json"
RESTART_EXIT_CODE = 75
_RESTART_SETTING_RE = re.compile(r"^(\\d+)\\s*(m|min|мин|h|ч|hour|час)?$")


def parse_restart_setting(text):
    """'off' -> 0, '20m'/'20' -> 20, '1h' -> 60, otherwise None (1 minute .. 24 hours)."""
    low = str(text or "").strip().lower()
    if low in {"off", "выкл", "0", "stop", "none"}:
        return 0
    match = _RESTART_SETTING_RE.match(low)
    if not match:
        return None
    value = int(match.group(1))
    minutes = value * 60 if (match.group(2) or "m") in {"h", "ч", "hour", "час"} else value
    return minutes if 1 <= minutes <= 24 * 60 else None


def restart_policy_minutes(base_dir):
    try:
        data = json.loads((Path(base_dir) / RESTART_POLICY_FILE_NAME).read_text(encoding="utf-8"))
        return max(0, int(data.get("interval_minutes") or 0))
    except Exception:
        return 0


def write_restart_policy(base_dir, minutes):
    path = Path(base_dir) / RESTART_POLICY_FILE_NAME
    path.write_text(json.dumps({"interval_minutes": int(minutes), "updated_at": time.time()},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def restart_drain_requested(base_dir):
    return (Path(base_dir) / RESTART_DRAIN_FILE_NAME).is_file()


def request_restart_drain(base_dir, reason=""):
    path = Path(base_dir) / RESTART_DRAIN_FILE_NAME
    if not path.is_file():
        path.write_text(json.dumps({"requested_at": time.time(), "reason": str(reason)}, ensure_ascii=False),
                        encoding="utf-8")


def clear_restart_drain(base_dir):
    try:
        (Path(base_dir) / RESTART_DRAIN_FILE_NAME).unlink()
    except FileNotFoundError:
        pass


def _restart_notify(text):
    """Durable Telegram notice; delivered by the controller's sender even across the restart."""
    try:
        chat = str(load_telegram_config().get("chat_id") or "").strip()
        if chat:
            _io1591.enqueue_notice(globals(), chat, str(text))
    except Exception as exc:
        print(f"[RESTART] Уведомление не поставлено в очередь: {type(exc).__name__}: {exc}", flush=True)


'''
OLD_WORKER_GATE = '''            else:
                try:
                    row = rows.get_nowait()
                except Exception:
                    worker["phase"] = "DONE"
'''
NEW_WORKER_GATE = '''            else:
                if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13
                    # The current row was finished to the end above; do not take a new one.
                    worker["phase"] = "RESTART_WAIT"
                    external_heartbeat(worker, "restart_wait")
                    set_tab_status(worker, "♻️", "Строка завершена; жду плановый перезапуск")
                    print(f"[Вкладка {tab_id}] Плановый перезапуск: строка завершена, новую не беру.", flush=True)
                    break
                try:
                    row = rows.get_nowait()
                except Exception:
                    worker["phase"] = "DONE"
'''
OLD_DEAD_SKIP = '''                    "DONE", "SUCCESS_STOP", "MANUAL_STOP",
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",
                } or bool(info.get("success_guard")) or bool(info.get("error_guard")):
'''
NEW_DEAD_SKIP = '''                    "DONE", "SUCCESS_STOP", "MANUAL_STOP", "RESTART_WAIT",
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",
                } or bool(info.get("success_guard")) or bool(info.get("error_guard")):
'''
OLD_CASCADE_HEAD = '''        # Для каждого Chromium свой последовательный cascade.
        while any(front in cascade_next for front in cascade_front.values()):
            ensure_ai_receiver_alive()
'''
NEW_CASCADE_HEAD = '''        # SCHEDULED_RESTART_1591R13: the timer opens a drain; while draining no new slot
        # or replacement worker is started, workers finish their rows and exit, and the
        # runtime then leaves with RESTART_EXIT_CODE for the controller to relaunch it.
        restart_started_at = monotonic()
        restart_notified = False

        def _restart_tick():
            nonlocal restart_notified
            if not restart_drain_requested(base_dir):
                minutes = restart_policy_minutes(base_dir)
                if minutes <= 0 or monotonic() - restart_started_at < minutes * 60:
                    return False
                request_restart_drain(base_dir, f"every {minutes} min")
                print(f"[RESTART] Прошло {minutes} мин: worker дорабатывают строки, новые не берут.", flush=True)
            if not restart_notified:
                restart_notified = True
                _restart_notify(
                    "♻️ Плановый перезапуск: worker дорабатывают текущие строки "
                    "(подтверждение, подпись, разбор DeepSeek), новые не берут; "
                    "когда все закончат, процесс перезапустится."
                )
            return True

        # Для каждого Chromium свой последовательный cascade.
        while any(front in cascade_next for front in cascade_front.values()):
            if _restart_tick():
                break
            ensure_ai_receiver_alive()
'''
OLD_FINAL_LOOP = '''            recover_dead_workers()

            # Успешная страница принадлежит общему Chromium и остаётся открытой.
            # Завершившийся SUCCESS_STOP-процесс заменяем новым процессом/вкладкой,
            # чтобы количество рабочих слотов не уменьшалось.
            replaced_success = False
            for tab_id, proc in list(processes.items()):
                if proc.is_alive():
                    continue
                info = heartbeat.get(str(tab_id)) or {}
                if info.get("phase") == "SUCCESS_STOP":
'''
NEW_FINAL_LOOP = '''            recover_dead_workers()
            draining = _restart_tick()  # SCHEDULED_RESTART_1591R13

            # Успешная страница принадлежит общему Chromium и остаётся открытой.
            # Завершившийся SUCCESS_STOP-процесс заменяем новым процессом/вкладкой,
            # чтобы количество рабочих слотов не уменьшалось.
            replaced_success = False
            for tab_id, proc in list(processes.items()):
                if proc.is_alive():
                    continue
                info = heartbeat.get(str(tab_id)) or {}
                if info.get("phase") == "SUCCESS_STOP" and not draining:
'''
OLD_QUEUE_DONE = '''        for proc in processes.values():
            proc.join(timeout=1)

        print(f"Все {TAB_COUNT} worker-слота завершили обработку очереди.")
'''
NEW_QUEUE_DONE = '''        for proc in processes.values():
            proc.join(timeout=1)

        if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13
            clear_restart_drain(base_dir)
            print("[RESTART] Все worker завершили строки; выхожу для планового перезапуска.", flush=True)
            _restart_notify("♻️ Все worker завершили строки. Перезапускаю процесс.")
            raise SystemExit(RESTART_EXIT_CODE)

        print(f"Все {TAB_COUNT} worker-слота завершили обработку очереди.")
'''
OLD_CTRL_CLASS = "class AutomationProcess:\n"
NEW_CTRL_CLASS = '''# SCHEDULED_RESTART_1591R13
def _restart_command(argument):
    """/restart, /restart off, /restart 20m, /restart 1h, /restart now."""
    argument = str(argument or "").strip().lower()
    if not argument:
        minutes = app.restart_policy_minutes(BASE_DIR)
        state = f"каждые {minutes} мин" if minutes > 0 else "выключен"
        pending = (" Сейчас ожидается перезапуск: worker дорабатывают строки."
                   if app.restart_drain_requested(BASE_DIR) else "")
        return (f"♻️ Плановый перезапуск: {state}.{pending}\\n"
                "Команды: /restart off, /restart 20m, /restart 1h, /restart now")
    if argument == "now":
        app.request_restart_drain(BASE_DIR, "manual")
        return ("♻️ Запрошен перезапуск: worker дорабатывают текущие строки, новые не берут; "
                "затем процесс перезапустится.")
    minutes = app.parse_restart_setting(argument)
    if minutes is None:
        return "Не понял интервал. Примеры: /restart off, /restart 20m, /restart 1h, /restart now"
    app.write_restart_policy(BASE_DIR, minutes)
    if minutes <= 0:
        return "♻️ Плановый перезапуск выключен."
    return (f"♻️ Плановый перезапуск включён: каждые {minutes} мин. Worker дорабатывают строки "
            "до конца (подтверждение, подпись, разбор DeepSeek), затем процесс перезапускается.")


def _restart_after_drain(proc):
    """Relaunch the automation that exited on purpose (RESTART_EXIT_CODE) after its drain."""
    if proc.proc is None or proc.proc.poll() != app.RESTART_EXIT_CODE:
        return False
    proc.proc = None
    ok, answer = proc.start()
    _send(("♻️ Плановый перезапуск выполнен. " if ok else "⚠️ Плановый перезапуск: запуск не удался. ") + answer)
    return True


class AutomationProcess:
'''
OLD_CTRL_SLASH = '''                    # Any slash-command belongs to controller namespace and is
                    # deliberately kept away from DeepSeek.
                    if text.startswith("/"):
'''
NEW_CTRL_SLASH = '''                    if text.startswith("/restart"):  # SCHEDULED_RESTART_1591R13
                        waiting_upload = False
                        _send(_restart_command(text[len("/restart"):]))
                        continue

                    # Any slash-command belongs to controller namespace and is
                    # deliberately kept away from DeepSeek.
                    if text.startswith("/"):
'''
OLD_CTRL_LOOP = "    while True:\n        proc.reap()\n"
OLD_TEST_CTRL_NS = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}',\n"
NEW_TEST_CTRL_NS = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}','_restart_after_drain':lambda p:False,\n"
NEW_CTRL_LOOP = "    while True:\n        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n        proc.reap()\n"
README_NOTE_R13 = '''

РЕВИЗИЯ 13 (fix_package_1591.py)
Плановый перезапуск. Команды в Telegram: /restart 20m (каждые 20 минут; можно 45, 1h),
/restart off (выключить), /restart now (запросить сейчас), /restart (показать настройку).
Настройка хранится в restart_policy.json и читается runtime на ходу, перезапуск для смены не
нужен. По таймеру runtime открывает «дренаж» (restart_drain.json): каждый worker доводит
текущую строку до конца (циклы подтверждения, подпись договора, разбор DeepSeek на
SUCCESS/ERROR-экране) и перед взятием новой строки останавливается с фазой RESTART_WAIT; новые
слоты и замены после SUCCESS_STOP не создаются. Когда живых worker не осталось, runtime
завершается кодом 75, контроллер видит этот код и запускает процесс заново, о начале и
завершении приходят уведомления. Пока хоть один worker занят строкой или разбором DeepSeek,
перезапуск ждёт. Маркер: SCHEDULED_RESTART_1591R13 (test_beeline.py и server_controller.py).
'''
# Revision 14: /registration/error reached from the post-auth review went to SUCCESS_ASSIST
# ("post-auth error page"), a branch with a success guard and no recovery, so the worker waited
# for ever. It now takes the registration/error policy of revision 5 like the confirmation
# and resend ticks do: analysis, then close, reopen, retry once, skip on repeat.
POSTAUTH_MARKER = "POST_AUTH_ERROR_ROUTE_1591R14"
OLD_POST_AUTH_ERROR = '''    # A real site error is not success, but even here we do NOT destroy/reload
    # the already-confirmed page. DeepSeek gets the page and decides how to help.
    if _post_auth_error_page(page):
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(
            worker, "🧠",
            "Подтверждение уже прошло. На post-auth странице ошибка — DeepSeek помогает."
        )
        external_heartbeat(worker, "success_post_auth_error")
        queue_success_assist(worker, "post-auth error page")
        return
'''
NEW_POST_AUTH_ERROR = '''    # POST_AUTH_ERROR_ROUTE_1591R14: /registration/error after auth is an ERROR under the
    # registration/error policy (revision 5): DeepSeek analyses, then the runtime closes
    # the tab, opens a new one and retries the row once; a repeat skips the row. This
    # used to become SUCCESS_ASSIST, which has no recovery, and the worker waited for ever.
    if _post_auth_error_page(page):
        capture_blackbox(worker, "registration_error_after_auth")
        print(
            f"[Вкладка {worker['id']}] На post-auth странице открылась /registration/error. "
            "Это НЕ success. Сначала DeepSeek анализирует страницу; затем runtime повторит "
            "строку по правилу registration/error.",
            flush=True,
        )
        enter_error_guard(
            worker,
            "после mobile-id-auth открылась /registration/error (post-auth review)",
        )
        return
'''
README_NOTE_R14 = '''

РЕВИЗИЯ 14 (fix_package_1591.py)
Ошибка регистрации на post-auth странице. Если /registration/error открывалась не сразу после
подтверждения, а уже в фазе POST_AUTH_REVIEW (после циклов «отправить снова»), worker уходил в
SUCCESS_ASSIST с пометкой «post-auth error page»: SUCCESS-guard, восстановления нет, worker
ждал бесконечно, а DeepSeek получал повторные платные запросы. Теперь такая страница
обрабатывается по правилу ревизии 5, как и в tick_confirmation/tick_resend: анализ DeepSeek,
затем закрытие вкладки, новая вкладка, один повтор строки, при повторе пропуск.
Маркер: POST_AUTH_ERROR_ROUTE_1591R14. Изменён tick_post_auth_review (переподписан в manifest).
'''
# Revision 15: a deterministic operator refusal on /registration/error (PERSDATA_NOT_MATCH:
# "данные не прошли проверку", "укажите другой свой номер") is skipped at once, without the
# paid DeepSeek analysis and without the retry that could only repeat the same refusal.
PERSDATA_MARKER = "PERSDATA_SKIP_1591R15"
OLD_ENTER_ERROR_GUARD = '''def enter_error_guard(worker, note):
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
NEW_ENTER_ERROR_GUARD = r'''# PERSDATA_SKIP_1591R15
ERROR_FINAL_NEEDLES_1591R15 = (
    ("данные не прошли проверку", "данные не прошли проверку у оператора"),
    ("укажите другой свой номер", "оператор просит указать другой номер"),
    ("persdata_not_match", "PERSDATA_NOT_MATCH"),
    ("не совпадают с данными", "данные не совпадают с базой оператора"),
)


def _error_page_final_reason(page):
    """Reason text when the error page is a deterministic operator refusal, else None."""
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        return None
    for needle, reason in ERROR_FINAL_NEEDLES_1591R15:
        if needle in body:
            return reason
    return None


def _error_skip_final(worker, reason):
    """Skip the row at once: a retry cannot change the operator's answer.

    Same steps as the second-error skip of ERROR_RECOVERY_1591R5, minus the analysis
    and the retry: fresh page, record in error_skipped_rows.txt, Telegram notice, IDLE.
    """
    key = _error_row_key(worker)
    base_dir = worker.get("base_dir") or Path(__file__).resolve().parent
    try:
        capture_blackbox(worker, "error_final_skip")
    except Exception:
        pass
    print(
        f"[Вкладка {worker['id']}] registration/error: {reason}. Повтор бессмыслен — "
        f"строка {key} пропускается без анализа.",
        flush=True,
    )
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        print(f"[Вкладка {worker['id']}] Новая вкладка не создана; строка {key} будет повторена.", flush=True)
        return False
    try:
        with (Path(base_dir) / "error_skipped_rows.txt").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{key}\t{reason}\n")
    except Exception:
        pass
    try:
        chat = str(load_telegram_config().get("chat_id") or "")
        if chat:
            _io1591.enqueue_notice(
                globals(), chat,
                f"⏭ Вкладка {worker['id']}: строка {key} пропущена без повтора: {reason}. "
                "Worker продолжает со следующей строкой.",
            )
    except Exception:
        pass
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена: {reason}. Беру следующую.")
    external_heartbeat(worker, "error_row_skipped_final")
    return True


def enter_error_guard(worker, note):
    # PERSDATA_SKIP_1591R15: a deterministic refusal is skipped at once, without the paid
    # analysis and without a retry that would only repeat the same answer.
    final = _error_page_final_reason(worker.get("page"))
    if final and _error_skip_final(worker, final):
        return
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
README_NOTE_R15 = '''

РЕВИЗИЯ 15 (fix_package_1591.py)
Отказ оператора без повтора. Если на /registration/error сайт пишет «данные не прошли
проверку» / «укажите другой свой номер» (в network это PERSDATA_NOT_MATCH: паспортные данные
строки не совпали с базой оператора), повтор строки даёт тот же ответ, но стоит новой капчи,
нового подтверждения у клиента и платного анализа DeepSeek. Теперь такая страница
распознаётся в enter_error_guard до постановки анализа в очередь: вкладка закрывается,
открывается новая, строка записывается в error_skipped_rows.txt с причиной, в Telegram уходит
уведомление «пропущена без повтора», worker берёт следующую строку. Все остальные ошибки
регистрации идут по правилу ревизии 5 без изменений. Маркер: PERSDATA_SKIP_1591R15.
'''
# Revision 16: every /registration/error after the confirmation is handled without DeepSeek:
# the tab is replaced and the row is skipped at once (the retry-once of revision 5 is gone).
ERRORSKIP_MARKER = "ERROR_SKIP_ALWAYS_1591R16"
OLD_GUARD_HEAD_R15 = '''def enter_error_guard(worker, note):
    # PERSDATA_SKIP_1591R15: a deterministic refusal is skipped at once, without the paid
    # analysis and without a retry that would only repeat the same answer.
    final = _error_page_final_reason(worker.get("page"))
    if final and _error_skip_final(worker, final):
        return
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
NEW_GUARD_HEAD_R16 = '''def enter_error_guard(worker, note):
    # ERROR_SKIP_ALWAYS_1591R16: every /registration/error after the confirmation is handled
    # without DeepSeek: the tab is replaced and the row is skipped at once. A page that names
    # the cause (PERSDATA_SKIP_1591R15) supplies the precise reason for the record.
    reason = _error_page_final_reason(worker.get("page")) or "registration/error после подтверждения"
    if _error_skip_final(worker, reason):
        return
    # No fresh page yet: the error tick repeats the skip after a short dwell, still without
    # an analysis request (the repeat-error branch of ERROR_RECOVERY_1591R5).
    worker.setdefault("error_retry_counts", {})[_error_row_key(worker)] = ERROR_ROW_MAX_ATTEMPTS - 1
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
OLD_GUARD_TAIL = '''    set_tab_status(
        worker, "🧠",
        "Registration error — DeepSeek сначала анализирует. Автоперезапуск запрещён."
    )
    external_heartbeat(worker, note)
    queue_error_assist(worker, note, force=True)
'''
NEW_GUARD_TAIL_R16 = '''    set_tab_status(
        worker, "♻️",
        "Registration error — вкладка будет перезапущена, строка пропущена. DeepSeek не вызывается."
    )
    external_heartbeat(worker, note)
'''
OLD_MISSION_R5_TEXT = ("ПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5): /registration/error — не успех, "
    "но и не вечное ожидание. Сначала детальный анализ страницы (DOM, текст ошибки, console/network) "
    "и мини-отчёт. После отчёта error-вкладка закрывается и открывается новая автоматически, без отдельного подтверждения: "
    "runtime делает это сразу после твоего отчёта и повторяет ту же строку один раз. "
    "При повторной ошибке на той же строке строка пропускается без нового анализа, worker берёт "
    "следующую. Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload "
    "остаётся только для SUCCESS_GUARD.\"\"\"\n")
NEW_MISSION_R16_TEXT = ("ПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5, ERROR_SKIP_ALWAYS_1591R16): "
    "/registration/error — не успех. Runtime обрабатывает её сам, автоматически, без отдельного подтверждения "
    "и без запроса к DeepSeek: error-вкладка закрывается, открывается новая, строка пропускается и записывается "
    "в error_skipped_rows.txt, worker берёт следующую. Анализировать такие страницы не нужно. "
    "Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload "
    "остаётся только для SUCCESS_GUARD.\"\"\"\n")
OLD_AGENT_BLOCK_R5 = '''ERROR SUPERVISOR:
- /registration/error НИКОГДА не является success.
- Сначала самостоятельно изучи DOM, видимый текст, console/network и последние ответы API.
  Определи конкретную причину и, если это безопасно, попробуй исправить на текущей странице.
- Затем отправь мини-отчёт: причина, что проверил, что попробовал, результат, URL.
- После детального анализа и отчёта error-вкладка закрывается и открывается новая
  АВТОМАТИЧЕСКИ, без отдельного подтверждения: runtime делает это сразу после твоего
  отчёта и повторяет ту же строку один раз. При повторной ошибке на той же строке
  строка пропускается, worker переходит к следующей.
- Из-за error worker никогда не теряется: слот всегда получает новую вкладку.
- Запрет close/restart/reload/back/navigate действует только на SUCCESS GUARD.
'''
NEW_AGENT_BLOCK_R16 = '''ERROR SUPERVISOR:
- /registration/error НИКОГДА не является success.
- Такие страницы runtime обрабатывает АВТОМАТИЧЕСКИ, без отдельного подтверждения и без
  твоего анализа: error-вкладка закрывается, открывается новая, строка пропускается
  (error_skipped_rows.txt), worker переходит к следующей.
- Не запрашивай и не проводи анализ /registration/error по своей инициативе.
- Из-за error worker никогда не теряется: слот всегда получает новую вкладку.
- Запрет close/restart/reload/back/navigate действует только на SUCCESS GUARD.
'''
OLD_QUEUE_SENTENCE_R5 = ('        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и повторит строку один раз; "\n'
                         '        "при повторной ошибке строка будет пропущена. Worker при этом не теряется. "\n')
NEW_QUEUE_SENTENCE_R16 = ('        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и пропустит строку без повтора. "\n'
                          '        "Worker при этом не теряется. "\n')
README_NOTE_R16 = '''

РЕВИЗИЯ 16 (fix_package_1591.py)
Ошибка регистрации без DeepSeek. Любая /registration/error после подтверждения теперь
обрабатывается runtime сразу и без анализа: вкладка закрывается, открывается новая, строка
пропускается с записью в error_skipped_rows.txt и уведомлением в Telegram, worker берёт
следующую. Повтор «один раз» из ревизии 5 убран: он стоил новой капчи, нового подтверждения у
клиента и платного анализа, а на волнах ошибок сайта давал те же ошибки. Если новую вкладку
создать не удалось, worker через 15 секунд повторяет пропуск (ветка повторной ошибки r5), тоже
без запроса к DeepSeek. Правило в системных инструкциях DeepSeek обновлено: анализировать такие
страницы не нужно. Причина на странице (r15) по-прежнему записывается в третью колонку.
Маркер: ERROR_SKIP_ALWAYS_1591R16.
'''
# Revision 17: "#успешно" on top of the SUCCESS push (searchable among the DeepSeek reports)
# and four worker tabs per Chromium instead of three.
SUCCESSTAG_MARKER = "SUCCESS_TAG_1591R17"
OLD_SUCCESS_HEAD = '''    return "\\n".join([
        f"✅ УСПЕХ — Вкладка {worker['id']}",
'''
NEW_SUCCESS_HEAD = '''    return "\\n".join([
        "#успешно",  # SUCCESS_TAG_1591R17: searchable among the DeepSeek reports
        f"✅ УСПЕХ — Вкладка {worker['id']}",
'''
OLD_TABS_LINE = "TABS_PER_BROWSER = 3\n"
NEW_TABS_LINE = "TABS_PER_BROWSER = 4  # SUCCESS_TAG_1591R17: four worker tabs\n"
README_NOTE_R17 = '''

РЕВИЗИЯ 17 (fix_package_1591.py)
Тег #успешно первой строкой SUCCESS-сообщения в Telegram, чтобы успехи искались среди
отчётов DeepSeek поиском по чату. Число рабочих вкладок на Chromium увеличено с 3 до 4
(TABS_PER_BROWSER = 4): каскад, статусы, watchdog и промпты DeepSeek берут число из
константы, поэтому больше ничего не менялось. Маркер: SUCCESS_TAG_1591R17.
'''
# Revision 18: a Chromium that stops answering CDP (connect_over_cdp timeouts on every
# watchdog attempt) is replaced as a whole, workers included. Also the literal "\n" in the
# watchdog's Telegram status text becomes a real line break.
BROWSER_MARKER = "BROWSER_HANG_1591R18"
OLD_WAIT_CDP = '''def _wait_cdp(port, timeout=25):
    deadline = monotonic() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    while monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False
'''
BROWSER_HELPERS_R18 = '''

# BROWSER_HANG_1591R18: a Chromium whose CDP socket accepts the connection but never
# answers (connect_over_cdp timeout) blocks every tab of that browser. The watchdog can
# only replace tabs, so after BROWSER_HANG_RESTART_SECONDS of continuous refusals the
# whole browser process is replaced on the same port and its workers are respawned.
BROWSER_HANG_RESTART_SECONDS = 120
_CDP_UNREACHABLE_SINCE = {}


def _note_cdp_result(cdp_url, exc, now=None):
    """Remember since when `cdp_url` refuses CDP commands; `exc=None` means it answered."""
    key = str(cdp_url)
    if exc is None:
        _CDP_UNREACHABLE_SINCE.pop(key, None)
        return
    text = f"{type(exc).__name__}: {exc}"
    if "connect_over_cdp" in text and "Timeout" in text:
        _CDP_UNREACHABLE_SINCE.setdefault(key, now if now is not None else monotonic())


def cdp_unreachable_seconds(cdp_url, now=None):
    since = _CDP_UNREACHABLE_SINCE.get(str(cdp_url))
    if since is None:
        return 0.0
    return (now if now is not None else monotonic()) - since


def _chromium_launch_args(chromium_exe, port, profile):
    """Same flags as args_i in main() (test_update checks that literal list stays there)."""
    return [
        chromium_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "about:blank",
    ]


def _terminate_chromium(instance):
    proc = instance.get("proc")
    try:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    except Exception:
        pass
    if instance.get("profile"):
        shutil.rmtree(str(instance["profile"]), ignore_errors=True)


def _relaunch_chromium(instance, chromium_exe, popen=None, wait_cdp=None, free_port=None):
    """Start a fresh Chromium for `instance`: the old port first (cdp_url stays valid for
    the observers), a free port as the fallback. Returns False when neither came up."""
    popen = popen or subprocess.Popen
    wait_cdp = wait_cdp or _wait_cdp
    free_port = free_port or _free_local_port
    for attempt in range(2):
        port = instance["port"] if attempt == 0 else free_port()
        profile = tempfile.mkdtemp(prefix=f"esim_pw_browser{instance['id']}_")
        instance["proc"] = popen(_chromium_launch_args(chromium_exe, port, profile))
        instance["profile"] = profile
        if wait_cdp(port):
            _CDP_UNREACHABLE_SINCE.pop(str(instance.get("cdp_url")), None)
            instance["port"] = port
            instance["cdp_url"] = f"http://127.0.0.1:{port}"
            _CDP_UNREACHABLE_SINCE.pop(instance["cdp_url"], None)
            return True
        _terminate_chromium(instance)
    return False
'''
OLD_CDP_CONNECT_R6 = '''                browser = p.chromium.connect_over_cdp(
                    cdp_url, timeout=int(timeout * 1000)
                )
'''
NEW_CDP_CONNECT_R18 = OLD_CDP_CONNECT_R6 + '''                _note_cdp_result(cdp_url, None)  # BROWSER_HANG_1591R18: the browser answered
'''
OLD_CDP_EXCEPT_R6 = '''        except Exception as exc:
            print(
                f"[WATCHDOG] Не удалось закрыть {expected_name}: "
'''
NEW_CDP_EXCEPT_R18 = '''        except Exception as exc:
            _note_cdp_result(cdp_url, exc)  # BROWSER_HANG_1591R18
            print(
                f"[WATCHDOG] Не удалось закрыть {expected_name}: "
'''
OLD_EXPERIMENT_LINE = '''    print("ЭКСПЕРИМЕНТ: запускаю 1 Chromium и 3 рабочие вкладки. Общая очередь строк.")
'''
NEW_EXPERIMENT_LINE = '''    print(f"Запускаю {BROWSER_COUNT} Chromium и {TAB_COUNT} рабочие вкладки. Общая очередь строк.")  # BROWSER_HANG_1591R18
'''
OLD_DEAD_HEAD = '''        def recover_dead_workers():
            """Restore capacity when a worker process died unexpectedly."""
'''
RESTART_BROWSER_FN_R18 = '''        def restart_browser_instance(browser_idx, reason):  # BROWSER_HANG_1591R18
            """Chromium stopped answering CDP: replace the browser process and its worker tabs.

            A tab still working a row gets the same row again. A tab under success/error
            guard, or one that already completed its confirm cycle, takes the next row so
            nothing is submitted twice. DONE / MANUAL_STOP / RESTART_WAIT slots stay as they are.
            When no Chromium comes up, the process exits with RESTART_EXIT_CODE and the
            controller relaunches everything.
            """
            instance = browser_instances[browser_idx]
            first_tab = browser_idx * TABS_PER_BROWSER + 1
            tab_ids = [t for t in range(first_tab, first_tab + TABS_PER_BROWSER) if t in processes]
            print(
                f"[BROWSER RESTART] Chromium #{instance['id']}: {reason} "
                f"Перезапускаю браузер и вкладки {tab_ids}.",
                flush=True,
            )
            plans = []
            for tab_id in tab_ids:
                proc = processes.get(tab_id)
                info = dict(heartbeat.get(str(tab_id)) or {})
                phase = str(info.get("phase") or "")
                if phase in {"DONE", "MANUAL_STOP", "RESTART_WAIT"}:
                    continue
                guarded = bool(info.get("success_guard")) or bool(info.get("error_guard")) or phase in {
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP", "ERROR_ASSIST",
                }
                row = None if (guarded or bool(info.get("completed_confirm_cycle"))) else info.get("row")
                plans.append((tab_id, row))
                try:
                    if proc is not None and proc.is_alive():
                        proc.terminate()
                        proc.join(timeout=5)
                        if proc.is_alive():
                            proc.kill()
                            proc.join(timeout=3)
                except Exception:
                    pass
                heartbeat.pop(str(tab_id), None)
                status_map[str(tab_id)] = {
                    "text": (
                        f"♻️ Вкладка {tab_id}\\nChromium перестал отвечать — браузер перезапущен.\\n"
                        + ("Повторяю эту же строку." if row is not None else "Беру следующую строку.")
                    ),
                    "time": time.time(),
                }
            _terminate_chromium(instance)
            if not _relaunch_chromium(instance, chromium_exe):
                print(
                    f"[BROWSER RESTART] Chromium #{instance['id']} не поднял CDP-порт; "
                    "выхожу для перезапуска процесса контроллером.",
                    flush=True,
                )
                _restart_notify(
                    f"⚠️ Chromium #{instance['id']} перестал отвечать ({reason}) и не запустился заново. "
                    "Перезапускаю весь процесс."
                )
                raise SystemExit(RESTART_EXIT_CODE)
            print(f"[BROWSER RESTART] Chromium #{instance['id']} готов: {instance['cdp_url']}", flush=True)
            _restart_notify(
                f"♻️ Chromium #{instance['id']} перестал отвечать ({reason}) Браузер перезапущен, "
                f"вкладки {[t for t, _ in plans]} пересозданы: строки в работе повторяются, "
                "завершённые берут следующую."
            )
            for tab_id, row in plans:
                new_proc, _ = spawn_worker(tab_id, row)
                processes[tab_id] = new_proc

'''
NEW_DEAD_HEAD = RESTART_BROWSER_FN_R18 + OLD_DEAD_HEAD
OLD_CLOSE_FAIL = '''                if not closed_old_tab:
                    print(
                        f"[WATCHDOG] TAB {tab_id}: старую вкладку закрыть не удалось; "
                        "replacement пока не создаю.",
                        flush=True,
                    )
                    continue
'''
NEW_CLOSE_FAIL = '''                if not closed_old_tab:
                    hang = cdp_unreachable_seconds(browser_instances[browser_idx]["cdp_url"])  # BROWSER_HANG_1591R18
                    if hang >= BROWSER_HANG_RESTART_SECONDS:
                        restart_browser_instance(
                            browser_idx,
                            f"CDP не отвечает {int(hang)} сек (вкладка {tab_id}: {reason})",
                        )
                        return True
                    print(
                        f"[WATCHDOG] TAB {tab_id}: старую вкладку закрыть не удалось; "
                        "replacement пока не создаю.",
                        flush=True,
                    )
                    continue
'''
OLD_STATUS_NL = r'''                        f"♻️ Вкладка {tab_id}\\n{reason}\\n"
'''
NEW_STATUS_NL = r'''                        f"♻️ Вкладка {tab_id}\n{reason}\n"  # BROWSER_HANG_1591R18: real line break
'''
README_NOTE_R18 = '''

РЕВИЗИЯ 18 (fix_package_1591.py)
Зависание всего Chromium. Когда браузер принимает CDP-соединение, но не отвечает на
команды (BrowserType.connect_over_cdp: Timeout), watchdog не мог закрыть ни одну вкладку и
крутился по кругу: «старую вкладку закрыть не удалось; replacement пока не создаю».
Теперь _close_cdp_page_for_worker отмечает такие отказы по адресу браузера
(_note_cdp_result / cdp_unreachable_seconds); если они длятся BROWSER_HANG_RESTART_SECONDS
(120 с), restart_browser_instance завершает worker этого браузера, убивает Chromium,
поднимает новый на том же порту (запасной вариант — свободный порт) и пересоздаёт вкладки:
строки в работе повторяются, вкладки под success/error guard и завершившие confirm берут
следующую строку, слоты DONE/MANUAL_STOP/RESTART_WAIT не трогаются. Если Chromium не
поднялся — выход с RESTART_EXIT_CODE, контроллер перезапускает процесс. Флаги запуска
Chromium повторены в _chromium_launch_args. В watchdog-статусе Telegram литеральный «\\n»
заменён настоящим переводом строки. Маркер: BROWSER_HANG_1591R18.
'''
# Revision 19: on the personal-data form the full name, the birth date and the four address
# inputs between «страна» and «дом» carry no label[for], name, id or descriptive placeholder;
# their captions sit in neighbouring elements. final_profile_capture_v1583 matched labels
# only, so those six fields stayed empty in the SUCCESS push. A companion capture records the
# nearest label-like text and the data-/aria-/autocomplete attributes of every control, and
# still-unlabeled fields fall back to value shape (name, birth date) and to position (the
# four address inputs). capture_all_form_fields_v1583 is a preserved handler and is untouched.
PROFILE_LABELS_MARKER = "PROFILE_LABELS_1591R19"
OLD_FINAL_CAPTURE_DEF = '''def final_profile_capture_v1583(page, worker):
    fields = capture_all_form_fields_v1583(page)
'''
PROFILE_LABEL_HELPERS_R19 = r'''# PROFILE_LABELS_1591R19
_FORM_FIELDS_JS_1591R19 = r"""() => {
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  const hasControl = el => !!(el && el.querySelector && el.querySelector('input,select,textarea'));
  const shortText = el => { const t = clean(el && (el.innerText || el.textContent)); return t && t.length <= 80 ? t : ''; };
  const out = [];
  for (const el of document.querySelectorAll('input,select,textarea')) {
    let near = '';
    try {
      // 1. the wrapper of exactly this control that carries a short caption (floating labels)
      let node = el.parentElement;
      for (let depth = 0; depth < 5 && !near && node; depth++) {
        if (node.querySelectorAll('input,select,textarea').length !== 1) break;
        near = shortText(node);
        node = node.parentElement;
      }
      // 2. the caption rendered just before the control or its wrapper; another control
      //    in between means the caption belongs to that other field
      node = el;
      for (let depth = 0; depth < 3 && !near && node; depth++) {
        let sib = node.previousElementSibling;
        while (sib && !near) {
          if (sib.matches('input,select,textarea') || hasControl(sib)) break;
          near = shortText(sib);
          sib = sib.previousElementSibling;
        }
        node = node.parentElement;
      }
    } catch (_) {}
    const attrs = [];
    try {
      for (const a of el.attributes) {
        if (/^(data-|aria-|autocomplete$|title$|role$)/.test(a.name) && a.value) attrs.push(a.name + '=' + a.value);
      }
      const by = el.getAttribute('aria-labelledby');
      if (by) for (const id of by.split(/\s+/)) { const l = document.getElementById(id); if (l) attrs.push('labelledby=' + clean(l.textContent)); }
    } catch (_) {}
    let value = '';
    try {
      value = (el.type === 'checkbox' || el.type === 'radio') ? (el.checked ? 'true' : 'false')
                                                              : String(el.value == null ? '' : el.value);
    } catch (_) {}
    let label = '';
    try {
      if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) label = clean(l.textContent); }
      if (!label) { const l = el.closest('label'); if (l) label = clean(l.textContent); }
    } catch (_) {}
    out.push({tag: (el.tagName || '').toLowerCase(), type: el.type || '', name: el.name || '', id: el.id || '',
              value, label, placeholder: el.placeholder || '', ariaLabel: el.getAttribute('aria-label') || '',
              near, attrs: attrs.join(' ')});
  }
  return out;
}"""


def capture_form_fields_1591r19(page):
    """capture_all_form_fields_v1583 plus `near` (the closest label-like text around the
    control) and `attrs` (data-/aria-/autocomplete attributes). Read-only."""
    try:
        data = page.evaluate(_FORM_FIELDS_JS_1591R19)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _alias_hit_1591r19(hay, word):
    """Short aliases («пол», «дом», «край», «ул.») must be whole words: «поле», «домашний»
    and «крайний» in a hint next to the field are not labels."""
    word = word.replace("ё", "е")
    if len(word) <= 4:
        return re.search(r"(?<![а-яa-z0-9])" + re.escape(word) + r"(?![а-яa-z0-9])", hay) is not None
    return word in hay


_DATE_FIELD_RE_1591R19 = re.compile(r"^\d{2}[.\-/]\d{2}[.\-/]\d{4}$")
_SKIP_FIELD_TYPES_1591R19 = {"checkbox", "radio", "hidden", "submit", "button", "password", "file"}


def _profile_fallback_1591r19(profile, fields, consumed):
    """Fields with no caption anywhere: the full name and the birth date by value shape, the
    four address inputs between «страна» and «дом» by their position on the form."""
    text_inputs = [(i, f) for i, f in enumerate(fields)
                   if str(f.get("tag") or "input").lower() == "input"
                   and str(f.get("type") or "text").lower() not in _SKIP_FIELD_TYPES_1591R19]
    issue_date = str(profile.get("passport_issue_date") or "").strip()
    for i, f in text_inputs:
        value = str(f.get("value") or "").strip()
        if i in consumed or not value:
            continue
        if not profile.get("full_name") and " " in value and _FIO_RE_1591R12.match(value):
            profile["full_name"] = value
            consumed.add(i)
            continue
        if (not profile.get("birth_date") and _DATE_FIELD_RE_1591R19.match(value) and value != issue_date
                and (_DATE_FIELD_RE_1591R19.match(str(f.get("placeholder") or "").strip())
                     or "рожд" in str(f.get("near") or "").lower())):
            profile["birth_date"] = value
            consumed.add(i)
    ids = [str(f.get("id") or "").lower() for f in fields]
    if "country" in ids and "house" in ids and ids.index("country") < ids.index("house"):
        a, b = ids.index("country"), ids.index("house")
        between = [(i, f) for i, f in text_inputs if a < i < b]
        if len(between) == 4:
            for (i, f), key in zip(between, ("region", "district", "locality", "street")):
                value = str(f.get("value") or "").strip()
                if i not in consumed and len(value) >= 2 and not profile.get(key):
                    profile[key] = value
                    consumed.add(i)
    return profile


'''
NEW_FINAL_CAPTURE_DEF = PROFILE_LABEL_HELPERS_R19 + OLD_FINAL_CAPTURE_DEF
OLD_ALIASES_HEAD = '''        "full_name": ("фио", "фамилия имя отчество", "fullname", "full_name"),
        "gender": ("пол", "gender"),
        "birth_date": ("дата рождения", "birth", "birthday"),
'''
NEW_ALIASES_HEAD = '''        "full_name": ("фио", "фамилия имя отчество", "фамилия", "ф.и.о", "ф. и. о", "fullname", "full_name",
                      "autocomplete=name"),  # PROFILE_LABELS_1591R19
        "gender": ("пол", "gender"),
        "birth_date": ("дата рождения", "дата рожд", "рождения", "birth", "birthday", "bday"),
'''
OLD_ALIASES_ADDRESS = '''        "region": ("область", "регион", "region"),
        "district": ("район", "district"),
        "locality": ("населённый пункт", "город", "city", "locality"),
        "street": ("улица", "street"),
'''
NEW_ALIASES_ADDRESS = '''        "region": ("область", "регион", "край", "республика", "region", "address-level1"),
        "district": ("район", "р-н", "district"),
        "locality": ("населённый пункт", "населенный пункт", "населённый", "населенный", "город", "city",
                     "locality", "address-level2"),
        "street": ("улица", "ул.", "street", "address-line1"),
'''
OLD_MATCH_LOOP = '''    for f in fields:
        value = str(f.get("value") or "").strip()
        if not value:
            continue
        hay = " ".join(str(f.get(k) or "") for k in
                       ("label", "name", "id", "placeholder", "ariaLabel")).lower()
        for key, words in aliases.items():
            if profile.get(key):
                continue
            if any(word in hay for word in words):
                profile[key] = value
                break
    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    return profile, fields
'''
NEW_MATCH_LOOP = '''    extended = capture_form_fields_1591r19(page)  # PROFILE_LABELS_1591R19
    if extended:
        try:
            d = worker.get("diagnostic")
            if d:
                d.write("form_fields_1591r19", fields=extended, url=page.url)
        except Exception:
            pass
    matched = extended or fields
    consumed = set()
    for index, f in enumerate(matched):
        value = str(f.get("value") or "").strip()
        if not value or str(f.get("type") or "").lower() in _SKIP_FIELD_TYPES_1591R19:
            continue
        hay = " ".join(str(f.get(k) or "") for k in
                       ("label", "name", "id", "placeholder", "ariaLabel", "near", "attrs")).lower().replace("ё", "е")
        for key, words in aliases.items():
            if profile.get(key):
                continue
            if any(_alias_hit_1591r19(hay, word) for word in words):
                profile[key] = value
                consumed.add(index)
                break
    _profile_fallback_1591r19(profile, matched, consumed)
    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    return profile, fields
'''
OLD_TEST_PROFILE_NS = """        ns={'_io1591':rt,'capture_all_form_fields_v1583':lambda p:fields}
        extract({'final_profile_capture_v1583'},ns)
"""
NEW_TEST_PROFILE_NS = """        ns={'_io1591':rt,'capture_all_form_fields_v1583':lambda p:fields,
            'capture_form_fields_1591r19':lambda p:[],'re':__import__('re'),  # PROFILE_LABELS_1591R19
            '_SKIP_FIELD_TYPES_1591R19':{'checkbox','radio','hidden'},
            '_DATE_FIELD_RE_1591R19':__import__('re').compile(r'^\\d{2}[.\\-/]\\d{2}[.\\-/]\\d{4}$'),
            '_FIO_RE_1591R12':__import__('re').compile(r'^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\\-]{0,30}(\\s+[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\\-]{0,30}){1,3}$')}
        extract({'final_profile_capture_v1583','_alias_hit_1591r19','_profile_fallback_1591r19'},ns)
"""
README_NOTE_R19 = '''

РЕВИЗИЯ 19 (fix_package_1591.py)
Данные профиля в SUCCESS-сообщении. Диагностика показала: на форме personal-data-form поля
ФИО, даты рождения и четыре адресных поля между «страна» и «дом» не имеют ни label[for], ни
name, ни id, ни осмысленного placeholder — подпись лежит в соседнем элементе. Захват
final_profile_capture_v1583 узнавал поля только по этим признакам, поэтому паспорт, страна,
дом и квартира попадали в отчёт, а ФИО, дата рождения, область, район, город и улица — нет.
Добавлен capture_form_fields_1591r19: к каждому полю записываются ближайший текст-подпись
(соседние элементы и родители) и data-/aria-/autocomplete-атрибуты; короткие алиасы («пол»,
«дом», «край») сравниваются как целые слова. Поля без подписи распознаются по форме значения
(ФИО, дата рождения с placeholder-датой) и по положению (четыре адресных поля между «страна»
и «дом»). Чекбоксы/radio/hidden в сопоставление не входят. Список полей с подписями пишется в
диагностику событием form_fields_1591r19. Сохранённый handler capture_all_form_fields_v1583
не менялся. Маркер: PROFILE_LABELS_1591R19.
'''
# Revision 20: a server outside Russia reaches Telegram directly. "proxy": "direct" (or none/off)
# in telegram_config.json means "no proxy on purpose": the code goes direct and the installer's
# r3 guard (which refuses an EMPTY proxy so the RU server never loses it by accident) accepts it.
PROXY_DIRECT_MARKER = "PROXY_DIRECT_1591R20"
TELEGRAM_DIRECT_PROXY_VALUES_SOURCE = "TELEGRAM_DIRECT_PROXY_VALUES = {\"direct\", \"none\", \"off\", \"no\", \"-\"}  # PROXY_DIRECT_1591R20: server outside RU\n"
OLD_PROXY_FN_DEF = "def telegram_http_proxies(cfg):\n"
NEW_PROXY_FN_DEF = TELEGRAM_DIRECT_PROXY_VALUES_SOURCE + "\n\n" + OLD_PROXY_FN_DEF
OLD_PROXY_EMPTY_CHECK = '''    ).strip()
    if not proxy:
        return None
    if "://" not in proxy:
'''
NEW_PROXY_EMPTY_CHECK = '''    ).strip()
    if not proxy or proxy.lower() in TELEGRAM_DIRECT_PROXY_VALUES:  # PROXY_DIRECT_1591R20
        return None
    if "://" not in proxy:
'''
README_NOTE_R20 = '''

РЕВИЗИЯ 20 (fix_package_1591.py)
Сервер вне России: Telegram доступен напрямую, прокси не нужен. В telegram_config.json
значение "proxy": "direct" (также none/off) означает «без прокси намеренно»: код идёт напрямую,
а защита установщика из ревизии 3 (пустой прокси по-прежнему отклоняется, чтобы российский
сервер не потерял его случайно) такое значение принимает. fresh_install.sh: на вопрос о прокси
можно ответить direct или просто Enter. Маркер: PROXY_DIRECT_1591R20.
'''
# Revision 21: the scheduled restart never relaunched. The automation exits with
# RESTART_EXIT_CODE (75) but xvfb-run (set -e, EXIT trap) reported 5 to the controller and left
# its Xvfb behind, so _restart_after_drain saw an "ordinary exit" and did nothing. Now the
# runtime writes restart_relaunch.json before exiting (and force-exits after 90 s if the normal
# shutdown hangs on child processes); the controller relaunches on the exit code OR on a fresh
# marker, remembers the last exit code even if reap() ran first, and kills the leftover
# process group (Xvfb) of the finished session.
RESTART_RELAUNCH_MARKER = "RESTART_RELAUNCH_1591R21"
OLD_CLEAR_DRAIN_R13 = """def clear_restart_drain(base_dir):
    try:
        (Path(base_dir) / RESTART_DRAIN_FILE_NAME).unlink()
    except FileNotFoundError:
        pass
"""
NEW_CLEAR_DRAIN_R21 = OLD_CLEAR_DRAIN_R13 + """

# RESTART_RELAUNCH_1591R21
RESTART_RELAUNCH_FILE_NAME = "restart_relaunch.json"
RESTART_EXIT_FORCE_SECONDS = 90


def request_relaunch(base_dir, reason=""):
    \"\"\"Ask the controller to start the automation again after this process exits.

    xvfb-run does not always pass RESTART_EXIT_CODE through, so the controller also looks at
    this marker. The timer forces the exit if the normal shutdown hangs on a child process.
    \"\"\"
    try:
        (Path(base_dir) / RESTART_RELAUNCH_FILE_NAME).write_text(
            json.dumps({"time": time.time(), "reason": str(reason)}, ensure_ascii=False), "utf-8"
        )
    except Exception as exc:
        print(f"[RESTART] Маркер перезапуска не записан: {type(exc).__name__}: {exc}", flush=True)
    import threading
    timer = threading.Timer(RESTART_EXIT_FORCE_SECONDS, lambda: os._exit(RESTART_EXIT_CODE))
    timer.daemon = True
    timer.start()
    return timer
"""
OLD_DRAIN_EXIT_R13 = """            _restart_notify("♻️ Все worker завершили строки. Перезапускаю процесс.")
            raise SystemExit(RESTART_EXIT_CODE)
"""
NEW_DRAIN_EXIT_R21 = """            _restart_notify("♻️ Все worker завершили строки. Перезапускаю процесс.")
            request_relaunch(base_dir, "drain complete")  # RESTART_RELAUNCH_1591R21
            raise SystemExit(RESTART_EXIT_CODE)
"""
OLD_BROWSER_EXIT_R18 = """                    "Перезапускаю весь процесс."
                )
                raise SystemExit(RESTART_EXIT_CODE)
"""
NEW_BROWSER_EXIT_R21 = """                    "Перезапускаю весь процесс."
                )
                request_relaunch(base_dir, "chromium relaunch failed")  # RESTART_RELAUNCH_1591R21
                raise SystemExit(RESTART_EXIT_CODE)
"""
OLD_CTRL_RELAUNCH_R13 = """def _restart_after_drain(proc):
    \"\"\"Relaunch the automation that exited on purpose (RESTART_EXIT_CODE) after its drain.\"\"\"
    if proc.proc is None or proc.proc.poll() != app.RESTART_EXIT_CODE:
        return False
    proc.proc = None
    ok, answer = proc.start()
"""
NEW_CTRL_RELAUNCH_R21 = """RELAUNCH_MARKER_MAX_AGE = 600  # RESTART_RELAUNCH_1591R21: a marker older than this is stale


def _relaunch_marker_fresh(marker):
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return False
    if age <= RELAUNCH_MARKER_MAX_AGE:
        return True
    try:
        marker.unlink()
    except OSError:
        pass
    return False


def _restart_after_drain(proc):
    \"\"\"Relaunch the automation that exited on purpose after its drain.

    RESTART_RELAUNCH_1591R21: the trigger is RESTART_EXIT_CODE from the process, the last code
    reap() recorded, or a fresh restart_relaunch.json written by the runtime before it exited
    (xvfb-run reported 5 instead of 75 on the server). A running process is never touched.
    \"\"\"
    if proc.running():
        return False
    marker = BASE_DIR / getattr(app, "RESTART_RELAUNCH_FILE_NAME", "restart_relaunch.json")
    code = proc.proc.poll() if proc.proc is not None else getattr(proc, "last_code", None)
    if code != app.RESTART_EXIT_CODE and not _relaunch_marker_fresh(marker):
        return False
    proc.reap()
    proc.last_code = None
    try:
        marker.unlink()
    except OSError:
        pass
    ok, answer = proc.start()
"""
OLD_CTRL_REAP = """    def reap(self):
        if self.proc is not None and self.proc.poll() is not None:
            code = self.proc.returncode
            self.proc = None
            print(f"[CTRL] automation завершилась code={code}", flush=True)
"""
NEW_CTRL_REAP_R21 = """    def reap(self):
        if self.proc is not None and self.proc.poll() is not None:
            code = self.proc.returncode
            pgid = self.proc.pid
            self.proc = None
            self.last_code = code  # RESTART_RELAUNCH_1591R21: kept for _restart_after_drain
            print(f"[CTRL] automation завершилась code={code}", flush=True)
            try:
                os.killpg(pgid, signal.SIGTERM)  # RESTART_RELAUNCH_1591R21: leftover Xvfb of that session
            except Exception:
                pass
"""
OLD_CTRL_INIT = """class AutomationProcess:
    def __init__(self):
        self.proc = None
"""
NEW_CTRL_INIT_R21 = """class AutomationProcess:
    def __init__(self):
        self.proc = None
        self.last_code = None  # RESTART_RELAUNCH_1591R21
"""
README_NOTE_R21 = """

РЕВИЗИЯ 21 (fix_package_1591.py)
Плановый перезапуск не выполнялся. Бот завершался с кодом RESTART_EXIT_CODE (75), но обёртка
xvfb-run (set -e и EXIT-trap) отдавала контроллеру код 5 и оставляла осиротевший Xvfb, поэтому
_restart_after_drain считал выход обычным и ничего не делал. Теперь перед выходом бот пишет
restart_relaunch.json (request_relaunch) и через 90 с принудительно завершается, если обычное
завершение зависло на дочерних процессах; контроллер перезапускает по коду выхода ИЛИ по
свежему маркеру (не старше 10 мин), помнит последний код даже если reap() сработал раньше, и
после завершения бота убивает остатки его группы процессов (Xvfb). Маркер: RESTART_RELAUNCH_1591R21.
"""
# Revision 22 (DeepSeek error report): (a) INVALID_ROW — the grey «Продолжить» was taken as the
# row's fault and the NEXT row was typed into the same used form (the same aggregateId across
# rows 257/258/259/265): now the row is retried once in a fresh tab, and after a second
# INVALID_ROW the next row also starts in a fresh tab; (b) rows skipped after registration/error
# were written to error_skipped_rows.txt but not to the progress file, so every scheduled
# restart put them back into the queue: both skip paths now record the row as processed.
ROW_SKIP_MARKER = "ROW_SKIP_PERSIST_1591R22"
OLD_RESET_STATE_DEF = "def reset_runtime_state(worker):\n"
INVALID_ROW_HELPERS_R22 = '''# ROW_SKIP_PERSIST_1591R22
INVALID_ROW_MAX_ATTEMPTS = 2


def _invalid_row_retry_1591r22(worker):
    """A grey «Продолжить» can be the form's stale state rather than the row's data (the same
    aggregateId was seen across many rows). Retry the row once in a fresh tab."""
    key = _error_row_key(worker)
    counts = worker.setdefault("invalid_row_counts", {})
    counts[key] = int(counts.get(key) or 0) + 1
    if counts[key] >= INVALID_ROW_MAX_ATTEMPTS:
        return False
    print(
        f"[Вкладка {worker['id']}] Строка {key}: «Продолжить» серая — повторяю её один раз в новой вкладке.",
        flush=True,
    )
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    set_tab_status(worker, "♻️", f"Строка {key}: форма не приняла данные; повтор в новой вкладке.")
    external_heartbeat(worker, "invalid_row_retry")
    return True


def _fresh_tab_for_next_row_1591r22(worker):
    """Skip the row; the next one starts in a fresh tab, never in the used form."""
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    reset_runtime_state(worker)
    worker["form_ready"] = False
    worker["phase"] = "IDLE"
    external_heartbeat(worker, "invalid_row_skipped")
    return True


'''
NEW_RESET_STATE_DEF = INVALID_ROW_HELPERS_R22 + OLD_RESET_STATE_DEF
OLD_FINISH_HEAD = '''    """Фиксирует результат и решает, можно ли этой вкладке брать следующую строку."""
    save_worker_result(base_dir, worker, status)

    if status == "INVALID_ROW":
        remember_processed_number(base_dir, worker.get("row"))
        worker["form_ready"] = True
        reset_runtime_state(worker)
        worker["phase"] = "IDLE"
        return
'''
NEW_FINISH_HEAD_R22 = '''    """Фиксирует результат и решает, можно ли этой вкладке брать следующую строку."""
    if status == "INVALID_ROW" and _invalid_row_retry_1591r22(worker):  # ROW_SKIP_PERSIST_1591R22
        return
    save_worker_result(base_dir, worker, status)

    if status == "INVALID_ROW":
        remember_processed_number(base_dir, worker.get("row"))
        if _fresh_tab_for_next_row_1591r22(worker):
            return
        worker["form_ready"] = True
        reset_runtime_state(worker)
        worker["phase"] = "IDLE"
        return
'''
OLD_R5_SKIP_TAIL = '''    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена после повторной registration/error. Беру следующую.")
'''
NEW_R5_SKIP_TAIL_R22 = '''    remember_processed_number(base_dir, worker.get("row"))  # ROW_SKIP_PERSIST_1591R22: not back after a restart
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена после повторной registration/error. Беру следующую.")
'''
OLD_R15_SKIP_TAIL = '''    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена: {reason}. Беру следующую.")
'''
NEW_R15_SKIP_TAIL_R22 = '''    remember_processed_number(base_dir, worker.get("row"))  # ROW_SKIP_PERSIST_1591R22: not back after a restart
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена: {reason}. Беру следующую.")
'''
README_NOTE_R22 = '''

РЕВИЗИЯ 22 (fix_package_1591.py)
По отчёту DeepSeek об ошибках. (а) INVALID_ROW: серая кнопка «Продолжить» считалась виной
строки, а следующая строка вводилась в ту же использованную форму (один aggregateId у строк
257/258/259/265). Теперь строка один раз повторяется в новой вкладке (_invalid_row_retry_1591r22);
после второго INVALID_ROW она пропускается, и следующая строка тоже начинается в новой вкладке
(_fresh_tab_for_next_row_1591r22). (б) Строки, пропущенные после registration/error, писались в
error_skipped_rows.txt, но не в файл прогресса, и каждый плановый перезапуск возвращал их в
очередь: оба пути пропуска теперь вызывают remember_processed_number. Маркер: ROW_SKIP_PERSIST_1591R22.
'''
# Revision 23: the SUCCESS record and push carry only the frozen eSIM-offer URL, which the
# site redirects to its start page outside the original browser session. The page the worker
# is on when the success is recorded (the signed contract) is now saved too — its URL and its
# document-like links (contract, PDF, QR, download) — as "final_url"/"final_links" in
# successful_sims.jsonl and as extra lines of the #успешно push. Diagnostics keep 40 sessions
# instead of 5: with a restart every 20 minutes, 5 sessions covered only a few hours.
FINAL_PAGE_MARKER = "FINAL_PAGE_1591R23"
OLD_DIAG_KEEP = "DIAGNOSTIC_SESSIONS_TO_KEEP = 5\n"
NEW_DIAG_KEEP = "DIAGNOSTIC_SESSIONS_TO_KEEP = 40  # FINAL_PAGE_1591R23: restarts every 20 min made 5 sessions a few hours\n"
OLD_WRITE_SUCCESS_HEAD = '''def write_success_record(base_dir, worker):
    n,a,b=row_parts(worker.get("row"))
    rec={
'''
FINAL_PAGE_HELPERS_R23 = r'''# FINAL_PAGE_1591R23
_FINAL_LINKS_JS_1591R23 = r"""() => {
  const out = [];
  const seen = new Set();
  const want = /договор|pdf|скачать|qr|esim|e-sim|загруз|документ|contract|download|профил|оплат|pay/i;
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  for (const el of document.querySelectorAll('a[href], [data-href], button[formaction]')) {
    const href = el.href || el.getAttribute('data-href') || el.getAttribute('formaction') || '';
    const text = clean(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('download'));
    if (!href || href.startsWith('javascript:') || seen.has(href)) continue;
    if (!(want.test(text) || want.test(href))) continue;
    seen.add(href);
    out.push({text: text.slice(0, 80), href: href.slice(0, 500)});
    if (out.length >= 8) break;
  }
  for (const img of document.querySelectorAll('img')) {
    const alt = clean(img.alt), src = String(img.src || '');
    if (!(/qr/i.test(alt) || /qr/i.test(src))) continue;
    out.push(src.startsWith('data:') ? {text: 'QR-код на странице (встроенное изображение)', href: ''}
                                     : {text: 'QR-код: ' + (alt || 'изображение'), href: src.slice(0, 500)});
    if (out.length >= 10) break;
  }
  let text = '';
  try { text = String((document.body && document.body.innerText) || ''); } catch (_) {}
  return {links: out, title: String(document.title || ''), text: text.slice(0, 20000)};
}"""


def capture_final_page_1591r23(page, worker=None):
    """URL of the page the worker is on when the success is recorded (the signed contract)
    plus its document-like links: contract, PDF, QR, download. Read-only."""
    result = {"url": "", "title": "", "links": []}
    if page is None:
        return result
    try:
        result["url"] = str(page.url or "")
    except Exception:
        pass
    text = ""
    try:
        data = page.evaluate(_FINAL_LINKS_JS_1591R23)
        if isinstance(data, dict):
            result["links"] = [x for x in (data.get("links") or []) if isinstance(x, dict)][:10]
            result["title"] = str(data.get("title") or "")[:200]
            text = str(data.get("text") or "")
    except Exception:
        pass
    if worker is not None:
        worker["final_url"] = result["url"]
        worker["final_title"] = result["title"]
        worker["final_links"] = result["links"]
        try:
            diagnostic = worker.get("diagnostic")
            if diagnostic:
                diagnostic.write("final_page_1591r23", url=result["url"], title=result["title"],
                                 links=result["links"], text=text[:20000])
        except Exception:
            pass
    return result


def _final_links_lines_1591r23(links):
    out = []
    for item in (links or [])[:10]:
        text = str((item or {}).get("text") or "").strip() or "документ"
        href = str((item or {}).get("href") or "").strip()
        out.append(f"{text}: {href}" if href else text)
    return out


'''
NEW_WRITE_SUCCESS_HEAD = FINAL_PAGE_HELPERS_R23 + '''def write_success_record(base_dir, worker):
    n,a,b=row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)  # FINAL_PAGE_1591R23
    rec={
'''
OLD_REC_PROFILE = '''        "profile":dict(worker.get("success_profile") or {}),
    }
'''
NEW_REC_PROFILE = '''        "profile":dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "",  # FINAL_PAGE_1591R23
        "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []),
    }
'''
OLD_SUCCESS_TAIL = '''        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
    ])
'''
NEW_SUCCESS_TAIL = '''        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        f"Страница договора: {rec.get('final_url') or '—'}",  # FINAL_PAGE_1591R23
        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
    ])
'''
README_NOTE_R23 = '''

РЕВИЗИЯ 23 (fix_package_1591.py)
Ссылка в записи об успехе — намеренно замороженный адрес страницы предложения eSIM, который вне
исходной сессии браузера сайт перенаправляет на начальную страницу. Теперь при фиксации успеха
сохраняется и страница, на которой стоит worker (подписанный договор): её адрес и ссылки на
документы (договор, PDF, QR, скачивание) — поля final_url/final_links в successful_sims.jsonl и
строки «Страница договора: …» и список документов в сообщении #успешно
(capture_final_page_1591r23); заголовок и текст финальной страницы пишутся в диагностику событием
final_page_1591r23, чтобы отличить подписанный договор от начальной страницы сайта.
Число хранимых сессий диагностики увеличено с 5 до 40: при
перезапуске каждые 20 минут 5 сессий покрывали лишь несколько часов. Маркер: FINAL_PAGE_1591R23.
'''
# Revision 24: a vanished «Подписать договор» button was the only success criterion, so a
# failed second signing attempt (button gone, TimeoutError) was recorded as a success within
# the same second (rows 5 and 134 on the second server; the eSIM links led to the start page).
# Success now needs positive evidence on the page (URL, text or a document link); without it
# the tab is held for UNVERIFIED_HOLD_SECONDS with DeepSeek asked to inspect, then recorded
# as UNVERIFIED: unverified_signatures.jsonl, a #неподтверждено push, the tab left open, the
# number NOT marked as processed.
SIGNED_MARKER = "SIGNED_EVIDENCE_1591R24"
OLD_SIGN_WAIT_DEF = "def tick_sign_wait(base_dir, worker):\n"
SIGNED_HELPERS_R24 = '''# SIGNED_EVIDENCE_1591R24
SIGNED_URL_HINTS_1591R24 = ("success", "complete", "done", "thank", "activation", "signed", "esim/ready")
SIGNED_TEXT_NEEDLES_1591R24 = (
    "договор подписан", "успешно подписан", "подписание завершено", "договор успешно",
    "договор отправлен", "спасибо за", "esim готова", "esim активирована", "qr-код", "скачать договор",
)
UNVERIFIED_HOLD_SECONDS = 180


def _signed_evidence_1591r24(page):
    """A positive sign of a signed contract on the page; a vanished button is not one."""
    try:
        url = str(page.url or "").lower()
    except Exception:
        url = ""
    if "personal-data" in url or "mobile-id" in url:
        return ""
    for hint in SIGNED_URL_HINTS_1591R24:
        if hint in url:
            return f"url:{hint}"
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        body = ""
    for needle in SIGNED_TEXT_NEEDLES_1591R24:
        if needle in body:
            return f"text:{needle}"
    try:
        if page.locator("a[href$='.pdf'], a[download]").count():
            return "link:document"
    except Exception:
        pass
    return ""


def _unverified_message_1591r24(worker, rec):
    row_no, active_value, second_value = row_parts(worker.get("row"))
    return "\\n".join([
        "#неподтверждено",
        f"⚠️ ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА — Вкладка {worker['id']}",
        f"Строка: {row_no}/{worker.get('total_rows') or '?'}",
        f"Исходные данные: {active_value} | {second_value}",
        f"Причина: {rec.get('reason') or '—'}",
        f"Страница: {rec.get('final_url') or '—'}",
        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        "",
        *_success_profile_lines(rec.get("profile")),
        "",
        f"eSIM: {rec.get('sim_number') or '—'}",
        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        "Номер НЕ помечен обработанным; вкладка оставлена открытой для проверки.",
    ])


def _finish_unverified_1591r24(base_dir, worker, reason):
    """The signing could not be confirmed: record it apart from the successes and stop the tab."""
    n, a, b = row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)
    rec = {
        "tab": worker["id"], "row": n, "active_digits": a, "second_value": b,
        "sim_number": worker.get("reserved_sim_number"), "sim_url": worker.get("reserved_sim_url"),
        "profile": dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "", "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []), "reason": str(reason or ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with (Path(base_dir) / "unverified_signatures.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    except Exception as exc:
        print(f"[Вкладка {worker['id']}] unverified_signatures.jsonl не записан: {type(exc).__name__}: {exc}", flush=True)
    worker["phase"] = "SUCCESS_STOP"
    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_unverified_message_1591r24(worker, rec))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить UNVERIFIED в очередь: {type(exc).__name__}: {exc}", flush=True)
    set_tab_status(
        worker, "⚠️",
        f"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\\n{reason}\\nСтраница: {rec['final_url'] or '—'}\\n"
        "Вкладка оставлена открытой. Для очереди будет создана новая.",
    )
    external_heartbeat(worker, "success_unverified_stop")
    print(
        f"\\n[Вкладка {worker['id']}] ⚠️ ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА. Строка {n}: {reason}. "
        "Номер не помечен обработанным; вкладка оставлена открытой.\\n",
        flush=True,
    )
    worker["stopped"] = True
    return rec


def settle_success_1591r24(base_dir, worker):
    """Called where the code used to declare success because no contract controls remained.

    With positive evidence the success is final (finalize_success). Without it the tab is
    held in SUCCESS_ASSIST for UNVERIFIED_HOLD_SECONDS (DeepSeek inspects, the button may
    reappear and be signed again), then the row is recorded as UNVERIFIED.
    """
    page = worker.get("page")
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
        worker["success_evidence"] = evidence
        finalize_success(base_dir, worker)
        return True
    now = monotonic()
    since = worker.get("success_unverified_since")
    url = ""
    try:
        url = str(page.url or "") if page is not None else ""
    except Exception:
        pass
    if since is None:
        worker["success_unverified_since"] = now
        try:
            capture_blackbox(worker, "success_unverified")
        except Exception:
            pass
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(
            worker, "⚠️",
            "Кнопка «Подписать договор» пропала, но признаков подписанного договора нет. "
            f"Держу вкладку {UNVERIFIED_HOLD_SECONDS // 60} мин, DeepSeek проверяет.",
        )
        external_heartbeat(worker, "success_unverified_hold")
        queue_success_assist(
            worker,
            "кнопка «Подписать договор» исчезла, но страница не похожа на подписанный договор: "
            f"проверь, подписан ли он, и что показано вместо кнопки (URL: {url})",
            force=True,
        )
        return False
    if now - since < UNVERIFIED_HOLD_SECONDS:
        worker["phase"] = "SUCCESS_ASSIST"
        return False
    _finish_unverified_1591r24(
        base_dir, worker,
        f"после «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не показала признаков подписания (URL: {url or '—'})",
    )
    return False


'''
NEW_SIGN_WAIT_DEF = SIGNED_HELPERS_R24 + OLD_SIGN_WAIT_DEF
OLD_SIGN_WAIT_FINAL = '''        if now - gone_since >= 1.2:
            finalize_success(base_dir, worker)
        return
'''
NEW_SIGN_WAIT_FINAL = '''        if now - gone_since >= 1.2:
            settle_success_1591r24(base_dir, worker)  # SIGNED_EVIDENCE_1591R24
        return
'''
OLD_REVIEW_FINAL = '''    # If we are post-auth and no contract controls remain, settle as success.
    finalize_success(base_dir, worker)
'''
NEW_REVIEW_FINAL = '''    # If we are post-auth and no contract controls remain, settle as success — only with
    # positive evidence of the signed contract (SIGNED_EVIDENCE_1591R24).
    settle_success_1591r24(base_dir, worker)
'''
README_NOTE_R24 = '''

РЕВИЗИЯ 24 (fix_package_1591.py)
Ложный успех подписи. Единственным признаком успеха было исчезновение кнопки «Подписать
договор»: на втором сервере строки 5 и 134 после неудачной второй попытки подписи (кнопка
пропала, TimeoutError) в ту же секунду записывались как успех, а ссылки eSIM вели на начальную
страницу. Теперь успех требует положительного признака на странице (_signed_evidence_1591r24:
адрес, текст или ссылка на документ). Без него settle_success_1591r24 держит вкладку
UNVERIFIED_HOLD_SECONDS (3 мин) в SUCCESS_ASSIST со снимком и задачей DeepSeek, затем пишет
строку в unverified_signatures.jsonl, шлёт в Telegram #неподтверждено с адресом, заголовком и
ссылками финальной страницы, оставляет вкладку открытой и НЕ помечает номер обработанным.
Заменены оба места фиксации успеха: tick_sign_wait и tick_post_auth_review. Маркер:
SIGNED_EVIDENCE_1591R24.
'''
# Revision 25: WHY the signing does not happen is not recorded anywhere — the click on
# «Подписать договор» leaves no trace of the server's answer. Around the click the page's
# responses (status, JSON/error bodies), failed requests and console errors are now collected
# for SIGN_TRACE_SECONDS, written to diagnostics (sign_click_trace_1591r25, plus a blackbox
# snapshot after the click), summarised into the success / unverified records and shown in
# the #неподтверждено push. Also: profile values without a letter or digit (a lone «.») are
# no longer accepted by the label matcher (the «Область: .» case).
SIGN_TRACE_MARKER = "SIGN_TRACE_1591R25"
OLD_SIGN_CALL_R14 = '''            capture_contract_details(page, worker)
            fill_signature_and_submit(page, worker.get("diagnostic"))
            worker["phase"] = "SIGN_WAIT"
'''
NEW_SIGN_CALL_R25 = '''            capture_contract_details(page, worker)
            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25
            try:
                fill_signature_and_submit(page, worker.get("diagnostic"))
            finally:
                _sign_trace_end_1591r25(page, worker)
            worker["phase"] = "SIGN_WAIT"
'''
OLD_SIGN_WAIT_DEF_R24 = "# SIGNED_EVIDENCE_1591R24\nSIGNED_URL_HINTS_1591R24 = "
SIGN_TRACE_HELPERS_R25 = '''# SIGN_TRACE_1591R25
SIGN_TRACE_SECONDS = 8
_SIGN_TRACE_SKIP_RE_1591R25 = re.compile(
    r"\\.(png|jpe?g|gif|svg|webp|css|js|woff2?|ttf|ico)(\\?|$)|metrika|analytics|google|flocktory|yandex|gtm",
    re.I,
)


def _sign_trace_begin_1591r25(page, worker):
    """Start collecting what the page does right after «Подписать договор» is clicked."""
    trace = {"started": time.time(), "url_before": "", "responses": [], "failed": [], "console": [],
             "_pending": [], "_handlers": {}}
    try:
        trace["url_before"] = str(page.url or "")
    except Exception:
        pass

    def on_response(resp):
        try:
            url = str(resp.url or "")
            if _SIGN_TRACE_SKIP_RE_1591R25.search(url) or len(trace["responses"]) >= 40:
                return
            item = {"t": round(time.time() - trace["started"], 2), "method": str(resp.request.method),
                    "status": int(resp.status), "url": url[:300]}
            trace["responses"].append(item)
            ctype = str(resp.headers.get("content-type", "") or "")
            if "json" in ctype or item["status"] >= 400 or item["method"] in ("POST", "PUT", "PATCH"):
                trace["_pending"].append((resp, item))
        except Exception:
            pass

    def on_failed(req):
        try:
            if len(trace["failed"]) < 20 and not _SIGN_TRACE_SKIP_RE_1591R25.search(str(req.url or "")):
                trace["failed"].append({"t": round(time.time() - trace["started"], 2), "url": str(req.url)[:300],
                                        "error": str(req.failure or "")[:200]})
        except Exception:
            pass

    def on_console(msg):
        try:
            if msg.type in ("error", "warning") and len(trace["console"]) < 30:
                trace["console"].append({"t": round(time.time() - trace["started"], 2), "type": str(msg.type),
                                         "text": str(msg.text)[:300]})
        except Exception:
            pass

    for event, fn in (("response", on_response), ("requestfailed", on_failed), ("console", on_console)):
        try:
            page.on(event, fn)
            trace["_handlers"][event] = fn
        except Exception:
            pass
    worker["sign_trace"] = trace
    return trace


def _sign_trace_end_1591r25(page, worker, note=""):
    """Wait SIGN_TRACE_SECONDS after the click, read the bodies, record the trace."""
    trace = worker.get("sign_trace")
    if not trace or "_handlers" not in trace:
        return trace
    deadline = monotonic() + SIGN_TRACE_SECONDS
    while monotonic() < deadline:
        try:
            page.wait_for_timeout(250)
        except Exception:
            break
    for event, fn in (trace.pop("_handlers", None) or {}).items():
        try:
            page.remove_listener(event, fn)
        except Exception:
            pass
    for resp, item in trace.pop("_pending", None) or []:
        try:
            item["body"] = re.sub(r"\\s+", " ", str(resp.text() or ""))[:1500]
        except Exception as exc:
            item["body_error"] = f"{type(exc).__name__}"
    try:
        trace["url_after"] = str(page.url or "")
    except Exception:
        trace["url_after"] = ""
    trace["note"] = str(note or "")
    try:
        diagnostic = worker.get("diagnostic")
        if diagnostic:
            diagnostic.write("sign_click_trace_1591r25", **{k: v for k, v in trace.items() if not k.startswith("_")})
    except Exception:
        pass
    try:
        capture_blackbox(worker, "after_sign_click")
    except Exception:
        pass
    print(
        f"[Вкладка {worker.get('id')}] SIGN TRACE: {trace['url_before']} -> {trace['url_after']}; "
        f"ответов {len(trace['responses'])}, сбоев сети {len(trace['failed'])}, console {len(trace['console'])}",
        flush=True,
    )
    return trace


def _sign_trace_summary_1591r25(trace):
    if not trace:
        return None
    keep = [r for r in trace.get("responses") or []
            if int(r.get("status") or 0) >= 400 or "body" in r or r.get("method") in ("POST", "PUT", "PATCH")]
    return {"url_before": trace.get("url_before") or "", "url_after": trace.get("url_after") or "",
            "responses": keep[:12], "failed": (trace.get("failed") or [])[:10], "console": (trace.get("console") or [])[:10]}


def _sign_trace_lines_1591r25(summary):
    if not summary:
        return []
    out = [f"Подпись: {summary.get('url_before') or '—'} → {summary.get('url_after') or '—'}"]
    for r in (summary.get("responses") or [])[:6]:
        line = f"  {r.get('method')} {r.get('url')} → {r.get('status')}"
        if r.get("body"):
            line += " " + str(r["body"])[:160]
        out.append(line)
    for f in (summary.get("failed") or [])[:3]:
        out.append(f"  сеть: {f.get('url')} — {f.get('error')}")
    for c in (summary.get("console") or [])[:3]:
        out.append(f"  console {c.get('type')}: {c.get('text')}")
    return out


'''
NEW_SIGN_WAIT_DEF_R25 = SIGN_TRACE_HELPERS_R25 + OLD_SIGN_WAIT_DEF_R24
OLD_UNVERIFIED_REC_R24 = '''        "final_links": list(final.get("links") or []), "reason": str(reason or ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
'''
NEW_UNVERIFIED_REC_R25 = '''        "final_links": list(final.get("links") or []), "reason": str(reason or ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),  # SIGN_TRACE_1591R25
    }
'''
OLD_UNVERIFIED_MSG_R24 = '''        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        "",
        *_success_profile_lines(rec.get("profile")),
'''
NEW_UNVERIFIED_MSG_R25 = '''        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        *_sign_trace_lines_1591r25(rec.get("sign_trace")),  # SIGN_TRACE_1591R25
        "",
        *_success_profile_lines(rec.get("profile")),
'''
OLD_SUCCESS_REC_R23 = '''        "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []),
    }
'''
NEW_SUCCESS_REC_R25 = '''        "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),  # SIGN_TRACE_1591R25
    }
'''
OLD_MATCH_SKIP_R19 = '''        if not value or str(f.get("type") or "").lower() in _SKIP_FIELD_TYPES_1591R19:
            continue
'''
NEW_MATCH_SKIP_R25 = '''        if not value or str(f.get("type") or "").lower() in _SKIP_FIELD_TYPES_1591R19:
            continue
        if not re.search(r"[0-9a-zа-яё]", value.lower()):  # SIGN_TRACE_1591R25: a lone «.» is not a value
            continue
'''
README_NOTE_R25 = '''

РЕВИЗИЯ 25 (fix_package_1591.py)
Почему подпись не проходит, было нечем установить: нажатие «Подписать договор» не оставляло
следа ответа сервера. Теперь вокруг нажатия SIGN_TRACE_SECONDS (8 с) собираются ответы страницы
(метод, статус, тела JSON и ошибок), сбои сети и ошибки console; всё пишется в диагностику
событием sign_click_trace_1591r25 и снимком after_sign_click, краткая выжимка попадает в записи
successful_sims.jsonl / unverified_signatures.jsonl (поле sign_trace) и в сообщение
#неподтверждено строками «Подпись: адрес → адрес» и ответами сервера. Строка
«[Вкладка N] SIGN TRACE: …» в журнале читается tools/sign_timeline.py. Значения профиля без
буквы или цифры (одиночная точка) больше не принимаются. Маркер: SIGN_TRACE_1591R25.
'''
# Revision 26: the "false successes" were the site's PAYMENT step. After «Подписать договор»
# the signature is accepted (checksignature 200, sendpassportdata… 202) and the page becomes
# «порядок, идём дальше → теперь пора оплатить eSIM … оплатите картой → дождитесь регистрации
# договора». The contract is registered only after payment; the runtime never knew the step
# and recorded a success. The payment page is now its own outcome: payment_required.jsonl,
# a #оплата push, the tab left open, the number marked as processed (no second order).
PAYMENT_MARKER = "PAYMENT_STEP_1591R26"
OLD_SETTLE_DEF_R24 = '''def settle_success_1591r24(base_dir, worker):
    """Called where the code used to declare success because no contract controls remained.
'''
PAYMENT_HELPERS_R26 = '''# PAYMENT_STEP_1591R26
PAYMENT_NEEDLES_1591R26 = (
    "пора оплатить", "оплатить картой", "оплатите картой", "дождитесь регистрации договора",
    "оплата esim", "оплатить esim", "к оплате",
)


def _payment_page_1591r26(page):
    """Text of the payment step when the site asks to pay for the eSIM after the signature."""
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "")
    except Exception:
        return ""
    low = body.lower()
    for needle in PAYMENT_NEEDLES_1591R26:
        if needle in low:
            start = max(0, low.index(needle) - 120)
            return re.sub(r"\\s+", " ", body[start:start + 360]).strip()
    return ""


def _payment_message_1591r26(worker, rec):
    row_no, active_value, second_value = row_parts(worker.get("row"))
    return "\\n".join([
        "#оплата",
        f"💳 ТРЕБУЕТСЯ ОПЛАТА eSIM — Вкладка {worker['id']}",
        f"Строка: {row_no}/{worker.get('total_rows') or '?'}",
        f"Исходные данные: {active_value} | {second_value}",
        "Подпись принята сайтом; договор регистрируется только после оплаты картой.",
        f"Текст шага: {rec.get('payment_text') or '—'}",
        f"Страница: {rec.get('final_url') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        *_sign_trace_lines_1591r25(rec.get("sign_trace")),
        "",
        *_success_profile_lines(rec.get("profile")),
        "",
        f"eSIM: {rec.get('sim_number') or '—'}",
        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        "Номер помечен обработанным (повтор создал бы второй заказ); вкладка оставлена открытой.",
    ])


def _finish_payment_required_1591r26(base_dir, worker, payment_text):
    """The site wants the eSIM paid: record it apart from the successes and stop the tab."""
    n, a, b = row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)
    rec = {
        "tab": worker["id"], "row": n, "active_digits": a, "second_value": b,
        "sim_number": worker.get("reserved_sim_number"), "sim_url": worker.get("reserved_sim_url"),
        "profile": dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "", "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []), "payment_text": str(payment_text or ""),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with (Path(base_dir) / "payment_required.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    except Exception as exc:
        print(f"[Вкладка {worker['id']}] payment_required.jsonl не записан: {type(exc).__name__}: {exc}", flush=True)
    remember_processed_number(base_dir, worker.get("row"))
    worker["phase"] = "SUCCESS_STOP"
    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_payment_message_1591r26(worker, rec))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить PAYMENT в очередь: {type(exc).__name__}: {exc}", flush=True)
    set_tab_status(
        worker, "💳",
        f"ТРЕБУЕТСЯ ОПЛАТА eSIM\\n{rec['payment_text'][:160]}\\nСтраница: {rec['final_url'] or '—'}\\n"
        "Вкладка оставлена открытой. Для очереди будет создана новая.",
    )
    external_heartbeat(worker, "payment_required_stop")
    print(
        f"\\n[Вкладка {worker['id']}] 💳 ТРЕБУЕТСЯ ОПЛАТА. Строка {n}: подпись принята, договор регистрируется "
        "после оплаты картой. Номер помечен обработанным; вкладка оставлена открытой.\\n",
        flush=True,
    )
    worker["stopped"] = True
    return rec


'''
NEW_SETTLE_DEF_R26 = PAYMENT_HELPERS_R26 + OLD_SETTLE_DEF_R24
OLD_SETTLE_HEAD_R24 = '''    page = worker.get("page")
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
'''
NEW_SETTLE_HEAD_R26 = '''    page = worker.get("page")
    payment_text = _payment_page_1591r26(page) if page is not None else ""  # PAYMENT_STEP_1591R26
    if payment_text:
        _finish_payment_required_1591r26(base_dir, worker, payment_text)
        return False
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
'''
README_NOTE_R26 = '''

РЕВИЗИЯ 26 (fix_package_1591.py)
«Ложные успехи» оказались шагом оплаты сайта. После «Подписать договор» подпись принимается
(checksignature 200, sendpassportdata… 202), а страница становится «порядок, идём дальше → теперь
пора оплатить eSIM … оплатите картой → дождитесь регистрации договора»: договор регистрируется
только после оплаты, код этого шага не знал и записывал успех. Теперь страница оплаты — отдельный
исход (_payment_page_1591r26 / _finish_payment_required_1591r26): запись в payment_required.jsonl,
сообщение #оплата с текстом шага, адресом, ссылками, ответами сервера и профилем, вкладка остаётся
открытой, номер помечается обработанным (повтор создал бы второй заказ). Проверяется до признаков
успеха в settle_success_1591r24. Маркер: PAYMENT_STEP_1591R26.
'''
# Revision 27: Telegram banned the bot for hours (429, retry after 16123 s). The status logger
# edited four tab messages as often as every second, ignored retry_after and kept retrying
# every second (which is how the ban grew), and every scheduled restart created four new
# messages. Now: one global gap between Bot API calls, at most one edit per tab per
# TG_STATUS_MIN_EDIT_GAP, a full stop for retry_after, status messages reused across restarts
# (telegram_status_messages.json), and the logger keeps running instead of giving up when the
# messages cannot be created at start.
TG_RATE_MARKER = "TG_RATE_1591R27"
OLD_LOGGER_DEF = "def telegram_logger_process(status_map, success_queue, stop_event):\n"
TG_RATE_HELPERS_R27 = '''# TG_RATE_1591R27
TG_MIN_CALL_GAP_1591R27 = 1.5
TG_STATUS_MIN_EDIT_GAP_1591R27 = 6.0


def _tg_status_file_1591r27():
    return TELEGRAM_CONFIG_FILE.with_name("telegram_status_messages.json")


def _tg_call_1591r27(cfg, method, payload, state):
    """One rate-limited Bot API call of the status logger: a global gap between calls and a
    full stop for retry_after when Telegram answers 429 (retrying every second grew the ban)."""
    now = time.time()
    if now < float(state.get("pause_until") or 0):
        return None, "paused"
    gap = TG_MIN_CALL_GAP_1591R27 - (now - float(state.get("last_call") or 0))
    if gap > 0:
        time.sleep(gap)
    state["last_call"] = time.time()
    r, err = telegram_api(cfg, method, payload)
    retry_after = getattr(err, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        state["pause_until"] = time.time() + float(retry_after) + 1
        print(f"[Telegram] 429: Telegram просит паузу {int(retry_after)} с — статусы не трогаю до её конца.", flush=True)
    return r, err


def _tg_status_messages_load_1591r27(chat):
    try:
        data = json.loads(_tg_status_file_1591r27().read_text("utf-8"))
        if str(data.get("chat")) == str(chat):
            return {int(k): int(v) for k, v in (data.get("mids") or {}).items()}
    except Exception:
        pass
    return {}


def _tg_status_messages_save_1591r27(chat, mids):
    try:
        _tg_status_file_1591r27().write_text(
            json.dumps({"chat": str(chat), "mids": {str(k): v for k, v in mids.items()}}), "utf-8"
        )
    except Exception:
        pass


def _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at):
    """Create the missing status messages and push the changed texts, within the limits."""
    changed = False
    for i in range(1, TAB_COUNT + 1):
        if i in mids:
            continue
        r, err = _tg_call_1591r27(
            cfg, "sendMessage",
            {"chat_id": chat, "text": f"⏳ Вкладка {i}\\nСтатус: запуск...", "disable_web_page_preview": "true"},
            state,
        )
        if r:
            mids[i] = r["result"]["message_id"]
            last[i] = ""
            changed = True
            print(f"[Telegram] Сообщение вкладки {i} создано.", flush=True)
        else:
            if err != "paused":
                print(f"[Telegram] ОШИБКА отправки вкладки {i}: {err}", flush=True)
            break
    if changed:
        _tg_status_messages_save_1591r27(chat, mids)
    now = time.time()
    for i, mid in list(mids.items()):
        info = status_map.get(str(i))
        t = str((info or {}).get("text", ""))
        if not t or t == last.get(i) or now - float(edited_at.get(i) or 0) < TG_STATUS_MIN_EDIT_GAP_1591R27:
            continue
        r, err = _tg_call_1591r27(
            cfg, "editMessageText",
            {"chat_id": chat, "message_id": mid, "text": t[:4000], "disable_web_page_preview": "true"},
            state,
        )
        edited_at[i] = time.time()
        if r:
            last[i] = t
            continue
        if err == "paused":
            break
        low = str(err).lower()
        if "message is not modified" in low:
            last[i] = t
        elif "not found" in low or "can't be edited" in low or "message_id_invalid" in low:
            mids.pop(i, None)
            _tg_status_messages_save_1591r27(chat, mids)
            print(f"[Telegram] Сообщение вкладки {i} исчезло — создам новое.", flush=True)
        else:
            print(f"[Telegram] ОШИБКА обновления вкладки {i}: {err}", flush=True)


'''
NEW_LOGGER_DEF = TG_RATE_HELPERS_R27 + OLD_LOGGER_DEF
OLD_LOGGER_STATE = '''    mids, last = {}, {}

    print("[Telegram] Логгер запущен.", flush=True)
'''
NEW_LOGGER_STATE = '''    mids, last = {}, {}
    state, edited_at = {"pause_until": 0.0, "last_call": 0.0}, {}  # TG_RATE_1591R27

    print("[Telegram] Логгер запущен.", flush=True)
'''
OLD_LOGGER_CREATE = '''    for i in range(1, TAB_COUNT + 1):
        t = f"⏳ Вкладка {i}\\nСтатус: запуск..."
        r, err = telegram_api(
            cfg, "sendMessage",
            {"chat_id": chat, "text": t, "disable_web_page_preview": "true"},
        )
        if r:
            mids[i] = r["result"]["message_id"]
            last[i] = t
            print(f"[Telegram] Сообщение вкладки {i} создано.", flush=True)
        else:
            print(f"[Telegram] ОШИБКА отправки вкладки {i}: {err}", flush=True)

    if not mids:
        print(
            "[Telegram] Не удалось создать ни одного сообщения. "
            "Основной сценарий продолжит работать без Telegram.",
            flush=True,
        )
        return

'''
NEW_LOGGER_CREATE = '''    # TG_RATE_1591R27: reuse the status messages of the previous run instead of four new ones
    # per restart; each is verified by an edit and recreated only when Telegram says it is gone.
    for i, mid in _tg_status_messages_load_1591r27(chat).items():
        r, err = _tg_call_1591r27(
            cfg, "editMessageText",
            {"chat_id": chat, "message_id": mid, "text": f"⏳ Вкладка {i}\\nСтатус: перезапуск...",
             "disable_web_page_preview": "true"},
            state,
        )
        if r or err == "paused" or "not modified" in str(err or "").lower():
            mids[i] = mid
            last[i] = ""
    _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)
    if not mids:
        print(
            "[Telegram] Статусные сообщения пока не созданы (лимит Telegram) — попробую позже; "
            "основной сценарий работает.",
            flush=True,
        )

'''
OLD_LOGGER_EDIT = '''        for i, mid in list(mids.items()):
            info = status_map.get(str(i))
            t = str((info or {}).get("text", ""))
            if t and t != last.get(i):
                r, err = telegram_api(
                    cfg, "editMessageText",
                    {
                        "chat_id": chat,
                        "message_id": mid,
                        "text": t[:4000],
                        "disable_web_page_preview": "true",
                    },
                )
                if r:
                    last[i] = t
                elif err and "message is not modified" not in err.lower():
                    print(f"[Telegram] ОШИБКА обновления вкладки {i}: {err}", flush=True)
        time.sleep(1)
'''
NEW_LOGGER_EDIT = '''        _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)  # TG_RATE_1591R27
        time.sleep(1)
'''
README_NOTE_R27 = '''

РЕВИЗИЯ 27 (fix_package_1591.py)
Telegram заблокировал бота на часы (429 Too Many Requests, retry after 16123 с). Логгер статусов
редактировал четыре сообщения вкладок хоть каждую секунду, не учитывал retry_after и продолжал
долбить каждую секунду (так штраф и вырос), а каждый плановый перезапуск создавал четыре новых
сообщения. Теперь: общий интервал между вызовами Bot API (TG_MIN_CALL_GAP_1591R27 = 1,5 с), не
чаще одной правки на вкладку в TG_STATUS_MIN_EDIT_GAP_1591R27 (6 с), полная пауза на retry_after,
статусные сообщения переиспользуются между перезапусками (telegram_status_messages.json), а если
их не удалось создать на старте, логгер не сдаётся и пробует позже. Маркер: TG_RATE_1591R27.
'''
# Revision 28: two Chromium instances with four tabs each (8 worker tabs). While four tabs
# wait up to 6.5 minutes for a mobile-id confirmation the other four keep the pipeline busy;
# a hung Chromium (r18) or a crash now takes down half the tabs, not all. Captchas of
# different tabs no longer pile up on the CPU: at most CAPTCHA_PARALLEL_MAX are solved at the
# same time, the other tabs wait for a slot and report CAPTCHA_WAIT so the watchdog does not
# take the wait for a stall.
TWO_BROWSERS_MARKER = "TWO_BROWSERS_1591R28"
OLD_BROWSER_COUNT = "BROWSER_COUNT = 1\n"
NEW_BROWSER_COUNT = '''# TWO_BROWSERS_1591R28
CAPTCHA_PARALLEL_MAX = 2            # captchas solved at the same time across all tabs
CAPTCHA_GATE_WAIT_SECONDS = 180     # longest wait for a slot; then the tab solves anyway
_CAPTCHA_GATE = None                # multiprocessing semaphore, set in each worker process

_try_local_captcha_unlocked = try_local_captcha


def try_local_captcha(page, frame_box=None):
    """Captchas of different tabs overlap at most CAPTCHA_PARALLEL_MAX at a time: a tab waits
    for a slot and reports CAPTCHA_WAIT to the watchdog meanwhile."""
    gate = _CAPTCHA_GATE
    if gate is None:
        return _try_local_captcha_unlocked(page, frame_box)
    from local_matcher import matcher_progress as _matcher_progress
    acquired = False
    deadline = monotonic() + CAPTCHA_GATE_WAIT_SECONDS
    try:
        while not acquired and monotonic() < deadline:
            acquired = bool(gate.acquire(timeout=5))
            if not acquired:
                try:
                    _matcher_progress("CAPTCHA_WAIT")
                except Exception:
                    pass
        return _try_local_captcha_unlocked(page, frame_box)
    finally:
        if acquired:
            try:
                gate.release()
            except Exception:
                pass


BROWSER_COUNT = 2  # TWO_BROWSERS_1591R28: two Chromium instances, TABS_PER_BROWSER tabs each
'''
OLD_TAB_PROCESS_DEF = "def _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None):\n"
NEW_TAB_PROCESS_DEF = "def _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None, captcha_gate=None):  # TWO_BROWSERS_1591R28\n"
OLD_CONFIGURE_MATCHER = "        configure_matcher_runtime(tab_id=tab_id, heartbeat=heartbeat)\n"
NEW_CONFIGURE_MATCHER = '''        configure_matcher_runtime(tab_id=tab_id, heartbeat=heartbeat)
        global _CAPTCHA_GATE
        _CAPTCHA_GATE = captcha_gate  # TWO_BROWSERS_1591R28
'''
OLD_PROCESSES_INIT = '''        processes = {}
        launch_events = [ctx.Event() for _ in range(TAB_COUNT)]
'''
NEW_PROCESSES_INIT = '''        processes = {}
        launch_events = [ctx.Event() for _ in range(TAB_COUNT)]
        captcha_gate = ctx.Semaphore(CAPTCHA_PARALLEL_MAX)  # TWO_BROWSERS_1591R28
'''
OLD_SPAWN_KWARGS = '''                    "diagnostic_session_dir": str(diagnostic_session_dir),
                    "success_queue": success_queue,
                },
                name=f"esim-tab-{tab_id}",
'''
NEW_SPAWN_KWARGS = '''                    "diagnostic_session_dir": str(diagnostic_session_dir),
                    "success_queue": success_queue,
                    "captcha_gate": captcha_gate,  # TWO_BROWSERS_1591R28
                },
                name=f"esim-tab-{tab_id}",
'''
README_NOTE_R28 = '''

РЕВИЗИЯ 28 (fix_package_1591.py)
Два Chromium по четыре вкладки (BROWSER_COUNT = 2, всего 8 рабочих вкладок): пока четыре вкладки
до 6,5 минуты ждут подтверждение mobile-id, другие четыре занимают конвейер; зависание или падение
браузера (ревизия 18) теперь задевает половину вкладок, а не все. Капчи разных вкладок больше не
накладываются: одновременно решаются не больше CAPTCHA_PARALLEL_MAX (2), остальные ждут слот
(семафор передаётся worker'ам, обёртка try_local_captcha) и на время ожидания шлют CAPTCHA_WAIT
в heartbeat, чтобы watchdog не считал это зависанием; после CAPTCHA_GATE_WAIT_SECONDS (180 с)
вкладка решает без слота. Маркер: TWO_BROWSERS_1591R28.
'''
# Revision 29: a drain file left by a run that was killed mid-drain (systemctl restart, crash)
# made the next run drain from its first second: every tab finished one row and waited for a
# restart. A drain belongs to the process that requested it, so a leftover file is discarded
# at start.
STALE_DRAIN_MARKER = "STALE_DRAIN_RESET_1591R29"
OLD_RESTART_TIMER_R13 = '''        restart_started_at = monotonic()
        restart_notified = False
'''
NEW_RESTART_TIMER_R29 = '''        restart_started_at = monotonic()
        restart_notified = False
        if restart_drain_requested(base_dir):  # STALE_DRAIN_RESET_1591R29
            clear_restart_drain(base_dir)
            print("[RESTART] Найден незавершённый drain прошлого запуска — сброшен, работаю как обычно.", flush=True)
'''
README_NOTE_R29 = '''

РЕВИЗИЯ 29 (fix_package_1591.py)
Файл restart_drain.json, оставшийся от процесса, убитого посреди планового перезапуска
(systemctl restart, падение), заставлял следующий запуск с первой секунды «дорабатывать строки
и ждать перезапуск»: каждая вкладка делала одну строку и вставала. Drain принадлежит
запросившему его процессу, поэтому при старте оставшийся файл сбрасывается с записью в журнал.
Маркер: STALE_DRAIN_RESET_1591R29.
'''
# Revision 30: the signing step made deterministic and coordinated with DeepSeek.
# (a) Before the local signing the portal overlays are dismissed (r6 helper, so far used for
#     tariff/eSIM only); after the click the r25 trace is checked for the signing request
#     (checksignature / POST) and, when nothing was sent and the button is still there, the
#     signature is redrawn and the button clicked ONCE more.
# (b) While a DeepSeek SUCCESS_ASSIST session works on the tab (ai_busy:<tab> in status_map,
#     set by the observer) the local code does not sign, for at most AI_YIELD_MAX_SECONDS.
# (c) DeepSeek's mandate: when the runtime's click did not go through it must dismiss overlays,
#     redraw, click once, verify the network answer and end its report with
#     «VERDICT: SIGNED | PAYMENT | NOT_SIGNED». The observer stores the verdict in status_map
#     (verdict:<tab>); settle_success uses SIGNED as evidence and PAYMENT as the payment step.
AI_VERDICT_MARKER = "AI_VERDICT_1591R30"
SIGN_ROBUST_MARKER = "SIGN_ROBUST_1591R31"  # the code part (r31); r30 is the prompt only
OLD_POST_AUTH_DEF = "def tick_post_auth_review(base_dir, worker):\n"
AI_VERDICT_HELPERS_R30 = r'''# SIGN_ROBUST_1591R31
AI_BUSY_MAX_SECONDS = 150      # a DeepSeek session older than this no longer blocks the local signing
AI_YIELD_MAX_SECONDS = 120     # the local code yields to DeepSeek at most this long per row
AI_VERDICT_MAX_AGE = 900
SIGN_SENT_RE_1591R30 = re.compile(r"checksignature|/sign", re.I)


def _ai_busy_1591r30(worker):
    """True while a DeepSeek SUCCESS_ASSIST session is working on this tab (bounded)."""
    sm = worker.get("status_map")
    if sm is None:
        return False
    try:
        info = sm.get(f"ai_busy:{worker.get('id')}") or {}
    except Exception:
        return False
    now = time.time()
    if not info or now - float(info.get("time") or 0) > AI_BUSY_MAX_SECONDS:
        worker["ai_yield_since"] = None
        return False
    since = worker.get("ai_yield_since")
    if since is None:
        worker["ai_yield_since"] = now
        return True
    return now - float(since) < AI_YIELD_MAX_SECONDS


def _ai_verdict_1591r30(worker):
    """DeepSeek's VERDICT for this tab, if given after the local click and still fresh."""
    sm = worker.get("status_map")
    if sm is None:
        return ""
    try:
        info = sm.get(f"verdict:{worker.get('id')}") or {}
    except Exception:
        return ""
    when = float(info.get("time") or 0)
    if not info or time.time() - when > AI_VERDICT_MAX_AGE:
        return ""
    if when < float(worker.get("sign_clicked_at") or 0):
        return ""
    return str(info.get("verdict") or "").upper()


def _ai_mark_busy_1591r30(status_map, request_text, update_id):
    """Observer side: this SUCCESS_ASSIST request is being worked on — the tab's local code yields."""
    m = re.search(r"\[AUTO_SUCCESS_ASSIST TAB (\d+)\]", str(request_text or ""))
    if not m or status_map is None:
        return None
    tab = int(m.group(1))
    try:
        status_map[f"ai_busy:{tab}"] = {"time": time.time(), "update": update_id}
    except Exception:
        pass
    return tab


def _ai_success_verdict_1591r30(status_map, request_text, response_text):
    """Observer side: record DeepSeek's VERDICT for the tab named in the request; clear busy."""
    m = re.search(r"\[AUTO_SUCCESS_ASSIST TAB (\d+)\]", str(request_text or ""))
    if not m or status_map is None:
        return None
    tab = int(m.group(1))
    try:
        status_map.pop(f"ai_busy:{tab}", None)
    except Exception:
        pass
    v = re.search(r"VERDICT:\s*(SIGNED|PAYMENT|NOT_SIGNED)", str(response_text or ""), re.I)
    if not v:
        return None
    verdict = v.group(1).upper()
    try:
        status_map[f"verdict:{tab}"] = {"verdict": verdict, "time": time.time(),
                                        "text": str(response_text or "")[-300:]}
    except Exception:
        pass
    print(f"[AI VERDICT] TAB {tab}: {verdict}", flush=True)
    return verdict


_SIGNATURE_CANVAS_FILLED_JS_1591R30 = r"""() => {
  const list = [...document.querySelectorAll('canvas')].filter(c => {
    const r = c.getBoundingClientRect(); return r.width >= 250 && r.height >= 120;
  });
  if (!list.length) return null;
  const c = list[0];
  try {
    const blank = document.createElement('canvas'); blank.width = c.width; blank.height = c.height;
    return c.toDataURL() !== blank.toDataURL();
  } catch (e) { return null; }
}"""


def _signature_canvas_filled_1591r30(page):
    """True/False when the signature pad is/is not drawn on; None when unknown."""
    try:
        return page.evaluate(_SIGNATURE_CANVAS_FILLED_JS_1591R30)
    except Exception:
        return None


def _sign_prepare_1591r30(page, worker):
    """Before the local signing: no portal modal may intercept the click."""
    try:
        dismiss_blocking_overlays(page, keep_text="подписать")
    except Exception:
        pass


def _sign_request_sent_1591r30(trace):
    for r in (trace or {}).get("responses") or []:
        url = str(r.get("url") or "")
        if SIGN_SENT_RE_1591R30.search(url):
            return True
        if str(r.get("method")) in ("POST", "PUT", "PATCH") and int(r.get("status") or 0) < 400 and "esim" in url.lower():
            return True
    return False


def _sign_retry_if_unsent_1591r30(page, worker):
    """The click sent nothing and the button is still there: overlays away, redraw, ONE more click."""
    trace = worker.get("sign_trace") or {}
    if _sign_request_sent_1591r30(trace) or int(worker.get("sign_retries") or 0) >= 1:
        return False
    try:
        if _signature_button_locator(page) is None:
            return False
    except Exception:
        return False
    worker["sign_retries"] = int(worker.get("sign_retries") or 0) + 1
    filled = _signature_canvas_filled_1591r30(page)
    canvas = "пуст" if filled is False else ("не пуст" if filled else "?")
    print(
        f"[Вкладка {worker.get('id')}] Подпись: запрос на сервер не ушёл (холст {canvas}) — "
        "снимаю оверлеи и повторяю один раз.",
        flush=True,
    )
    _sign_prepare_1591r30(page, worker)
    _sign_trace_begin_1591r25(page, worker)
    try:
        fill_signature_and_submit(page, worker.get("diagnostic"))
        worker["sign_clicked_at"] = time.time()
        return True
    except Exception as exc:
        print(f"[Вкладка {worker.get('id')}] Повтор подписи не удался: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        return False
    finally:
        _sign_trace_end_1591r25(page, worker, note="retry")


'''
NEW_POST_AUTH_DEF = AI_VERDICT_HELPERS_R30 + OLD_POST_AUTH_DEF
OLD_BUTTON_BLOCK = '''    button = _signature_button_locator(page)
    if button is not None:
        try:
            enabled = button.is_enabled()
'''
NEW_BUTTON_BLOCK_R30 = '''    button = _signature_button_locator(page)
    if button is not None and _ai_busy_1591r30(worker):  # SIGN_ROBUST_1591R31: DeepSeek is on this tab
        set_tab_status(worker, "🧠", "Подтверждение успешно. DeepSeek работает с вкладкой — подпись отложена.")
        external_heartbeat(worker, "sign_yield_to_ai")
        return
    if button is not None:
        try:
            enabled = button.is_enabled()
'''
OLD_SIGN_CALL_R25 = '''            capture_contract_details(page, worker)
            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25
            try:
                fill_signature_and_submit(page, worker.get("diagnostic"))
            finally:
                _sign_trace_end_1591r25(page, worker)
            worker["phase"] = "SIGN_WAIT"
'''
NEW_SIGN_CALL_R30 = '''            capture_contract_details(page, worker)
            _sign_prepare_1591r30(page, worker)  # SIGN_ROBUST_1591R31: overlays away first
            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25
            try:
                fill_signature_and_submit(page, worker.get("diagnostic"))
            finally:
                _sign_trace_end_1591r25(page, worker)
            worker["sign_clicked_at"] = time.time()
            try:
                _sign_retry_if_unsent_1591r30(page, worker)  # nothing sent + button still there → one retry
            except Exception as exc:
                print(f"[Вкладка {worker['id']}] Проверка отправки подписи: {type(exc).__name__}: {exc}", flush=True)
            worker["phase"] = "SIGN_WAIT"
'''
OLD_OBSERVER_PRINT = '''        print(
            f"[AI {lane.upper()}] Обрабатываю update {update_id}: {latest[:120]}",
            flush=True,
        )
'''
NEW_OBSERVER_PRINT = '''        print(
            f"[AI {lane.upper()}] Обрабатываю update {update_id}: {latest[:120]}",
            flush=True,
        )
        _ai_mark_busy_1591r30(status_map, latest, update_id)  # SIGN_ROBUST_1591R31
'''
OLD_OBSERVER_COMPLETE = '''            # Mark complete and queue the response in one local durable store.
            _ai_db_complete(
'''
NEW_OBSERVER_COMPLETE = '''            _ai_success_verdict_1591r30(status_map, latest, response_text)  # SIGN_ROBUST_1591R31
            # Mark complete and queue the response in one local durable store.
            _ai_db_complete(
'''
OLD_OBSERVER_FAIL = '''            _ai_db_fail(update_id, err, job.get("attempts", 1))
'''
NEW_OBSERVER_FAIL = '''            _ai_db_fail(update_id, err, job.get("attempts", 1))
            _ai_success_verdict_1591r30(status_map, latest, "")  # SIGN_ROBUST_1591R31: busy flag off
'''
OLD_SETTLE_PAYMENT_R26 = '''    if payment_text:
        _finish_payment_required_1591r26(base_dir, worker, payment_text)
        return False
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
'''
NEW_SETTLE_PAYMENT_R30 = '''    if payment_text:
        _finish_payment_required_1591r26(base_dir, worker, payment_text)
        return False
    verdict = _ai_verdict_1591r30(worker)  # SIGN_ROBUST_1591R31
    if verdict == "PAYMENT":
        _finish_payment_required_1591r26(base_dir, worker, "по вердикту DeepSeek: сайт требует оплату eSIM")
        return False
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if not evidence and verdict == "SIGNED":
        evidence = "ai:verdict_signed"
    if evidence:
'''
OLD_ASSIST_TAIL = '''        "Подписание прошло успешно. Вкладка осталась на …». "
        f"Причина вызова: {reason}. Текущий URL: {url}"
    )
'''
NEW_ASSIST_TAIL_R30 = '''        "Подписание прошло успешно. Вкладка осталась на …». "
        "ЕСЛИ RUNTIME УЖЕ НАЖАЛ «Подписать договор», а страница не изменилась или кнопка осталась: "  # AI_VERDICT_1591R30
        "сними всплывающие окна, перерисуй подпись, нажми кнопку ОДИН раз и проверь в network ответ "
        "/checksignature/. Пока статус вкладки ✍️ (runtime сам рисует и нажимает) — не кликай. "
        "ПОСЛЕДНЯЯ СТРОКА ОТЧЁТА СТРОГО одна из: «VERDICT: SIGNED» (checksignature 200 или экран после "
        "подписи), «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина». "
        f"Причина вызова: {reason}. Текущий URL: {url}"
    )
'''
OLD_MISSION_BULLET = "- После нажатия снова наблюдай страницу/console/network и проверь фактический результат.\n"
NEW_MISSION_BULLET_R30 = '''- После нажатия снова наблюдай страницу/console/network и проверь фактический результат.
- Если runtime уже нажал «Подписать договор», а страница не изменилась или кнопка осталась:
  сними всплывающие окна, перерисуй подпись, нажми кнопку ОДИН раз, проверь ответ
  /checksignature/ в network. Пока статус вкладки ✍️ — runtime сам рисует и нажимает, не кликай.
- Последняя строка каждого отчёта SUCCESS SUPERVISOR СТРОГО одна из: «VERDICT: SIGNED»,
  «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина».
  Runtime читает эту строку: SIGNED фиксирует успех, PAYMENT — шаг оплаты, NOT_SIGNED —
  вкладка удерживается и уходит на проверку пользователю.
'''
OLD_TEST_OBSERVER_NS = "            '_ai_db_fail':lambda *a:(_ for _ in ()).throw(AssertionError(a))}\n"
NEW_TEST_OBSERVER_NS = ("            '_ai_db_fail':lambda *a:(_ for _ in ()).throw(AssertionError(a)),\n"
                        "            '_ai_mark_busy_1591r30':lambda *a:None,'_ai_success_verdict_1591r30':lambda *a:None}  # SIGN_ROBUST_1591R31\n")
README_NOTE_R30 = '''

РЕВИЗИЯ 30 (fix_package_1591.py)
Только промпт DeepSeek (код сценария не менялся). Мандат SUCCESS SUPERVISOR: если runtime уже нажал
«Подписать договор», а страница не изменилась или кнопка осталась — снять всплывающие окна,
перерисовать подпись, нажать кнопку ОДИН раз, проверить ответ /checksignature/ в network; пока
статус вкладки ✍️ — не кликать. Последняя строка каждого отчёта строго «VERDICT: SIGNED |
PAYMENT | NOT_SIGNED». Маркер: AI_VERDICT_1591R30.
'''
README_NOTE_R31 = '''

РЕВИЗИЯ 31 (fix_package_1591.py)
Код подписи. (а) Перед локальной подписью снимаются оверлеи сайта (помощник ревизии 6, раньше
только для тарифа и eSIM); после клика по следу ревизии 25 проверяется, ушёл ли запрос подписи
(checksignature / POST), и если нет, а кнопка на месте — подпись перерисовывается и кнопка
нажимается ещё ОДИН раз (_sign_retry_if_unsent_1591r30, холст _signature_canvas_filled_1591r30).
(б) Пока сессия DeepSeek SUCCESS_ASSIST работает с вкладкой (ai_busy:<tab> в status_map, ставит
наблюдатель), локальный код не подписывает, не дольше AI_YIELD_MAX_SECONDS (120 с). (в) Наблюдатель
пишет вердикт DeepSeek в status_map (verdict:<tab>); settle_success считает SIGNED признаком успеха,
PAYMENT — шагом оплаты. Собирается по умолчанию; FIX_1591_MAX_REVISION=30 собирает пакет без этой
части. Маркер: SIGN_ROBUST_1591R31.
'''
# ---- revision 32 ----
# Revision 32: (a) the tariff card is looked for inside the «выберите тариф» picker and a card must
#     hold exactly one tariff title with a visible «выбрать» (the shared basket already showing
#     TARIFF_NAME made every tab of that Chromium fail with RECOVERABLE_RESTART_ROW forever);
#     (b) same-row restarts are capped and the row goes to the back of the queue; (c) a drain
#     has a deadline, so half the tabs can no longer wait forever for a looping worker.
TARIFF_SCOPE_MARKER = "TARIFF_SCOPE_1591R32"
ROW_RESTART_LIMIT_MARKER = "ROW_RESTART_LIMIT_1591R32"
DRAIN_DEADLINE_MARKER = "DRAIN_DEADLINE_1591R32"
OLD_TARIFF_FINDER_R32 = 'def _tariff_choose_button(page, diagnostic=None, timeout=10000):\n    """«выбрать» inside the card titled TARIFF_NAME; the card order is never assumed."""\n    title = page.get_by_text(TARIFF_NAME, exact=True).first\n    try:\n        title.wait_for(state="visible", timeout=timeout)\n        card = title.locator(\n            "xpath=ancestor::*[.//button[normalize-space(.)=\'выбрать\' or normalize-space(.)=\'Выбрать\']][1]"\n        )\n        button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n        if button.count() > 0:\n            return button.first\n    except Exception:\n        pass\n    try:\n        titles = page.locator("text=/подписка/i").all_inner_texts()[:10]\n        choose_count = page.get_by_role("button", name=_CHOOSE_BUTTON_RE).count()\n    except Exception:\n        titles, choose_count = [], -1\n    if diagnostic is not None:\n        try:\n            diagnostic.write("tariff_card_not_found", tariff=TARIFF_NAME, titles=titles, choose_buttons=choose_count)\n        except Exception:\n            pass\n    print(\n        f"Карточка «{TARIFF_NAME}» с кнопкой «выбрать» не найдена; на экране: {titles}, "\n        f"кнопок «выбрать»: {choose_count}",\n        flush=True,\n    )\n    raise RuntimeError(\n        f"RECOVERABLE_RESTART_ROW: карточка тарифа «{TARIFF_NAME}» с кнопкой «выбрать» не найдена."\n    )\n'
NEW_TARIFF_FINDER_R32 = 'def _tariff_choose_button(page, diagnostic=None, timeout=10000):\n    """«выбрать» inside the card titled TARIFF_NAME; the card order is never assumed.\n\n    TARIFF_SCOPE_1591R32: the basket already holding TARIFF_NAME (chosen by an earlier row in the\n    same Chromium: the basket is shared by its tabs) shows the same title with «изменить» and no\n    «выбрать»; the tariff is looked for inside the «выберите тариф» picker first, and a card is only\n    the element around the title that holds exactly one tariff title and a visible «выбрать».\n    """\n    scopes = []\n    try:\n        header = page.get_by_text(_TARIFF_PICKER_HEADER_RE_1591R32).first\n        if header.count() > 0:\n            picker = header.locator(\n                "xpath=ancestor::*[.//*[normalize-space(.)=\'" + TARIFF_NAME + "\']][1]"\n            )\n            if picker.count() > 0:\n                scopes.append(picker)\n    except Exception:\n        pass\n    scopes.append(page)\n    deadline = monotonic() + timeout / 1000.0\n    while True:\n        for scope in scopes:\n            try:\n                button = _tariff_card_button_1591r32(scope)\n            except Exception:\n                button = None\n            if button is not None:\n                return button\n        if monotonic() >= deadline:\n            break\n        page.wait_for_timeout(300)\n    try:\n        titles = page.locator("text=/подписка/i").all_inner_texts()[:10]\n        choose_count = page.get_by_role("button", name=_CHOOSE_BUTTON_RE).count()\n    except Exception:\n        titles, choose_count = [], -1\n    if diagnostic is not None:\n        try:\n            diagnostic.write("tariff_card_not_found", tariff=TARIFF_NAME, titles=titles, choose_buttons=choose_count)\n        except Exception:\n            pass\n    print(\n        f"Карточка «{TARIFF_NAME}» с кнопкой «выбрать» не найдена; на экране: {titles}, "\n        f"кнопок «выбрать»: {choose_count}",\n        flush=True,\n    )\n    raise RuntimeError(\n        f"RECOVERABLE_RESTART_ROW: карточка тарифа «{TARIFF_NAME}» с кнопкой «выбрать» не найдена."\n    )\n\n\n# TARIFF_SCOPE_1591R32\n_TARIFF_PICKER_HEADER_RE_1591R32 = re.compile(r"^\\s*выберите тариф\\s*$", re.I)\n_TARIFF_TITLE_RE_1591R32 = re.compile(r"^\\s*подписка bee\\b", re.I)\n_TARIFF_BASKET_BUTTON_RE_1591R32 = re.compile(r"^\\s*(изменить|удалить тариф)\\s*$", re.I)\n\n\ndef _tariff_card_button_1591r32(scope):\n    """The visible «выбрать» of the one card titled TARIFF_NAME inside `scope`, else None."""\n    titles = scope.get_by_text(TARIFF_NAME, exact=True)\n    for index in range(min(titles.count(), 8)):\n        title = titles.nth(index)\n        try:\n            if not title.is_visible():\n                continue\n            card = title.locator(\n                "xpath=ancestor::*[.//button[normalize-space(.)=\'выбрать\' or normalize-space(.)=\'Выбрать\']][1]"\n            )\n            if card.count() == 0:\n                continue\n            if card.get_by_text(_TARIFF_TITLE_RE_1591R32).count() != 1:\n                continue  # a container of several cards (or the basket plus the picker), not a card\n            if card.get_by_role("button", name=_TARIFF_BASKET_BUTTON_RE_1591R32).count() > 0:\n                continue  # the basket card («изменить» / «Удалить тариф»): its «выбрать» belong to options\n            button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n            if button.count() > 0 and button.first.is_visible():\n                return button.first\n        except Exception:\n            continue\n    return None\n'
OLD_ROW_READY_R32 = '                if worker["phase"] == "RESTART_ROW_READY":\n                    print(\n                        f"[Вкладка {tab_id}] Новая physical-вкладка готова. "\n                        "Повторяю ту же строку с начала.",\n                        flush=True,\n                    )\n                    continue\n'
NEW_ROW_READY_R32 = '                if worker["phase"] == "RESTART_ROW_READY":\n                    if _row_restart_exhausted_1591r32(worker, row, rows):  # ROW_RESTART_LIMIT_1591R32\n                        break\n                    print(\n                        f"[Вкладка {tab_id}] Новая physical-вкладка готова. "\n                        "Повторяю ту же строку с начала.",\n                        flush=True,\n                    )\n                    continue\n'
OLD_RESET_DEF_R32 = 'def reset_runtime_state(worker):\n'
NEW_RESET_DEF_R32 = '# ROW_RESTART_LIMIT_1591R32\nROW_RESTART_MAX = 3            # same-row restarts (new tab, same row) before the row is put back\nROW_DEFER_MAX_PER_RUN = 2      # a row is put back at most this many times per process launch\nDEFERRED_ROWS_FILE_NAME = "deferred_rows.jsonl"\n\n\ndef _row_restart_exhausted_1591r32(worker, row, rows):\n    """Count same-row restarts; past ROW_RESTART_MAX the row goes to the back of the queue\n    and the slot (already on a fresh page) takes the next one. The number is not marked\n    processed, so the row is tried again later in this run or at the next launch."""\n    key = _row_number_value(row) if row is not None else ""\n    counter = worker.get("row_restarts_1591r32") or {}\n    attempts = int(counter.get(key) or 0) + 1\n    worker["row_restarts_1591r32"] = {key: attempts}\n    if attempts <= ROW_RESTART_MAX:\n        return False\n    tab_id = worker.get("id")\n    line_number, active_digits, _ = row_parts(row)\n    deferred = int(row.get("_deferred_1591r32") or 0) + 1 if isinstance(row, dict) else 1\n    requeued = False\n    if isinstance(row, dict) and deferred <= ROW_DEFER_MAX_PER_RUN and rows is not None:\n        row["_deferred_1591r32"] = deferred\n        try:\n            rows.put(row)\n            requeued = True\n        except Exception as exc:\n            print(f"[Вкладка {tab_id}] Строка {line_number} не вернулась в очередь: {type(exc).__name__}: {exc}", flush=True)\n    note = ("вернул в конец очереди" if requeued\n            else "оставил до следующего запуска (номер не помечен обработанным)")\n    print(\n        f"[Вкладка {tab_id}] Строка {line_number}: {ROW_RESTART_MAX} перезапуска подряд не помогли; "\n        f"{note}, беру следующую.",\n        flush=True,\n    )\n    try:\n        base_dir = worker.get("base_dir")\n        if base_dir:\n            with open(Path(base_dir) / DEFERRED_ROWS_FILE_NAME, "a", encoding="utf-8") as handle:\n                handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": tab_id,\n                                         "row": line_number, "number": active_digits,\n                                         "restarts": attempts - 1, "requeued": requeued},\n                                        ensure_ascii=False) + "\\n")\n    except Exception:\n        pass\n    worker["row_restarts_1591r32"] = {}\n    set_tab_status(worker, "⏭", f"Строка {line_number}: перезапуски исчерпаны, {note}")\n    reset_runtime_state(worker)\n    worker["form_ready"] = False\n    worker["phase"] = "IDLE"\n    external_heartbeat(worker, "row_deferred")\n    return True\n\n\ndef reset_runtime_state(worker):\n'
OLD_DRAIN_TICK_R32 = '            draining = _restart_tick()  # SCHEDULED_RESTART_1591R13\n'
NEW_DRAIN_TICK_R32 = '            draining = _restart_tick()  # SCHEDULED_RESTART_1591R13\n            if draining:\n                _drain_deadline_1591r32(base_dir, processes, heartbeat)  # DRAIN_DEADLINE_1591R32\n'
OLD_LOAD_PROCESSED_R32 = 'def load_processed_numbers(base_dir):\n'
NEW_LOAD_PROCESSED_R32 = '# ROW_RESTART_LIMIT_1591R32 (parent side)\nROW_RESPAWN_MAX = 3            # replacements of a worker with the same row per launch\n_ROW_RESPAWNS_1591R32 = {}\n\n\ndef _row_for_respawn_1591r32(saved_row, tab_id, base_dir, why):\n    """The row a replacement worker starts with: the same row up to ROW_RESPAWN_MAX times per\n    launch (DEAD RECOVERY and the watchdog together), then None: the row stays unprocessed for\n    the next launch and the new worker takes the next one. Without this a row that always\n    hangs the tab (CANCELLING -> watchdog -> same row) looped forever."""\n    if saved_row is None:\n        return None\n    try:\n        key = _row_number_value(saved_row)\n    except Exception:\n        key = str(saved_row)\n    count = _ROW_RESPAWNS_1591R32.get(key, 0) + 1\n    _ROW_RESPAWNS_1591R32[key] = count\n    if count <= ROW_RESPAWN_MAX:\n        return saved_row\n    line_number, active_digits, _ = row_parts(saved_row)\n    print(\n        f"[Вкладка {tab_id}] Строка {line_number}: worker заменялся с этой строкой уже {count - 1} раз "\n        f"({why}); оставляю её до следующего запуска (номер не помечен обработанным), "\n        "новый worker берёт следующую.",\n        flush=True,\n    )\n    try:\n        with open(Path(base_dir) / DEFERRED_ROWS_FILE_NAME, "a", encoding="utf-8") as handle:\n            handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": tab_id,\n                                     "row": line_number, "number": active_digits,\n                                     "respawns": count - 1, "requeued": False, "why": why},\n                                    ensure_ascii=False) + "\\n")\n    except Exception:\n        pass\n    return None\n\n\n# DRAIN_DEADLINE_1591R32\nDRAIN_SOFT_MAX_SECONDS = 15 * 60   # then workers still at the start of a row are stopped\nDRAIN_HARD_MAX_SECONDS = 40 * 60   # then every remaining worker is stopped\nDRAIN_PROTECTED_PHASES = {\n    "POST_CONTINUE", "AUTH_WAIT", "CONFIRM", "RESEND", "PROTECTED_CHECK",\n    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",\n}\n\n\ndef _drain_age_1591r32(base_dir):\n    try:\n        data = json.loads((Path(base_dir) / RESTART_DRAIN_FILE_NAME).read_text(encoding="utf-8"))\n        return max(0.0, time.time() - float(data.get("requested_at") or 0.0))\n    except Exception:\n        return 0.0\n\n\ndef _drain_deadline_1591r32(base_dir, processes, heartbeat):\n    """A drain must end. After DRAIN_SOFT_MAX_SECONDS a worker that is still at the start of\n    a row (tariff, eSIM, form: nothing sent to the subscriber yet) is stopped; its row is not\n    marked processed and is taken again at the next launch. Confirmation, signing and DeepSeek\n    review are waited for until DRAIN_HARD_MAX_SECONDS. Returns the stopped tab ids."""\n    age = _drain_age_1591r32(base_dir)\n    if age < DRAIN_SOFT_MAX_SECONDS:\n        return []\n    stopped = []\n    for tab_id, proc in list(processes.items()):\n        if proc is None or not proc.is_alive():\n            continue\n        info = dict(heartbeat.get(str(tab_id)) or {})\n        phase = str(info.get("phase") or "")\n        protected = (phase in DRAIN_PROTECTED_PHASES or bool(info.get("success_guard"))\n                     or bool(info.get("error_guard")))\n        if protected and age < DRAIN_HARD_MAX_SECONDS:\n            continue\n        line_number = row_parts(info.get("row"))[0] if info.get("row") is not None else "?"\n        print(\n            f"[RESTART] Дренаж идёт {int(age // 60)} мин: вкладка {tab_id} на этапе {phase or \'unknown\'} "\n            f"(строка {line_number}) остановлена; номер не помечен обработанным и вернётся в очередь "\n            "при новом запуске.",\n            flush=True,\n        )\n        try:\n            proc.terminate()\n            proc.join(timeout=5)\n        except Exception:\n            pass\n        info["phase"] = "RESTART_WAIT"   # neither DEAD RECOVERY nor the watchdog replaces it\n        try:\n            heartbeat[str(tab_id)] = info\n        except Exception:\n            pass\n        stopped.append(tab_id)\n    return stopped\n\n\ndef load_processed_numbers(base_dir):\n'
README_NOTE_R32 = '\n\nРЕВИЗИЯ 32 (fix_package_1591.py)\n(а) Карточка тарифа. Корзина общая для вкладок одного Chromium: когда прошлая строка уже выбрала\n«подписка bee START», на странице два одинаковых заголовка — в корзине (с «изменить», без\n«выбрать») и в окне «выберите тариф». Прежний поиск брал первый заголовок и падал с\nRECOVERABLE_RESTART_ROW; теперь тариф ищется в окне «выберите тариф», карточкой считается\nэлемент вокруг заголовка ровно с одним названием тарифа и видимой «выбрать»\n(_tariff_card_button_1591r32). (б) Предел перезапусков строки: после ROW_RESTART_MAX (3)\nперезапусков одной строки в новой вкладке строка возвращается в конец очереди (не более двух раз\nза запуск, затем остаётся до следующего запуска), номер не помечается обработанным, слот берёт\nследующую; запись в deferred_rows.jsonl. Тот же предел (ROW_RESPAWN_MAX = 3) на стороне watchdog и\nDEAD RECOVERY: worker, зависший в CANCELLING, заменялся новым с той же строкой бесконечно. (в) Срок дренажа: через DRAIN_SOFT_MAX_SECONDS (15 мин)\nпосле начала планового перезапуска вкладки, всё ещё на старте строки, останавливаются (строка\nвернётся при новом запуске); подтверждение, подпись, разбор DeepSeek ждутся до\nDRAIN_HARD_MAX_SECONDS (40 мин). Маркеры: TARIFF_SCOPE_1591R32, ROW_RESTART_LIMIT_1591R32,\nDRAIN_DEADLINE_1591R32.\n'
OLD_DEAD_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else saved_row,\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        def recover_stalled_workers():\n'
NEW_DEAD_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else _row_for_respawn_1591r32(saved_row, tab_id, base_dir, "dead recovery"),  # ROW_RESTART_LIMIT_1591R32\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        def recover_stalled_workers():\n'
OLD_STALL_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else saved_row,\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        last_ai_restart_at = {}\n'
NEW_STALL_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else _row_for_respawn_1591r32(saved_row, tab_id, base_dir, "watchdog"),  # ROW_RESTART_LIMIT_1591R32\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        last_ai_restart_at = {}\n'
# Revision 33: the basket shows several «изменить»; the tariff one is clicked, not the region one.
TARIFF_CHANGE_MARKER = "TARIFF_CHANGE_BUTTON_1591R33"
OLD_TARIFF_CHANGE_R33 = '            candidates = [\n                page.get_by_role("button", name="изменить", exact=True),\n                page.locator("button").filter(has_text=re.compile(r"^\\s*изменить\\s*$", re.I)),\n            ]\n'
NEW_TARIFF_CHANGE_R33 = '            candidates = [  # TARIFF_CHANGE_BUTTON_1591R33: the tariff «изменить», not the region one\n                _tariff_change_button_1591r33(page),\n                page.get_by_role("button", name="изменить", exact=True),\n                page.locator("button").filter(has_text=re.compile(r"^\\s*изменить\\s*$", re.I)),\n            ]\n'
OLD_TARIFF_HELPER_ANCHOR_R33 = '# TARIFF_SCOPE_1591R32\n_TARIFF_PICKER_HEADER_RE_1591R32 = re.compile(r"^\\s*выберите тариф\\s*$", re.I)\n'
NEW_TARIFF_HELPER_R33 = '# TARIFF_CHANGE_BUTTON_1591R33\n_TARIFF_CHANGE_METRIC_1591R33 = \'button[data-metric-name="basketMetric:handleClickChangeTariffButton"]\'\n\n\ndef _tariff_change_button_1591r33(page):\n    """Locator of the tariff block\'s «изменить». The basket can show several «изменить» (the region\n    block «Саратов • изменить» comes first) and the first one opened the region picker, not the\n    tariff picker. Preference: the site\'s own tariff-change button when it is marked, else the\n    «изменить» nearest to a tariff title («подписка bee …»), else every «изменить» (the caller\n    clicks the first). Any «изменить» is waited for first, so a late render does not fall through."""\n    generic = page.get_by_role("button", name="изменить", exact=True)\n    try:\n        expect(generic.first).to_be_visible(timeout=20000)\n    except Exception:\n        return generic\n    try:\n        marked = page.locator(_TARIFF_CHANGE_METRIC_1591R33)\n        if marked.count() > 0:\n            return marked\n    except Exception:\n        pass\n    try:\n        titles = page.get_by_text(_TARIFF_TITLE_RE_1591R32)\n        for index in range(min(titles.count(), 4)):\n            near = titles.nth(index).locator(\n                "xpath=ancestor::*[.//button[normalize-space(.)=\'изменить\']][1]"\n            ).get_by_role("button", name="изменить", exact=True)\n            if near.count() > 0:\n                return near\n    except Exception:\n        pass\n    return generic\n\n\n# TARIFF_SCOPE_1591R32\n_TARIFF_PICKER_HEADER_RE_1591R32 = re.compile(r"^\\s*выберите тариф\\s*$", re.I)\n'
README_NOTE_R33 = '\n\nРЕВИЗИЯ 33 (fix_package_1591.py)\nКнопка «изменить» тарифа. В корзине бывает несколько «изменить» (первая — у региона «Саратов»);\nкод нажимал первую, открывался выбор региона, а не тарифов, и карточка тарифа «не находилась»,\nпока строка не отдавалась (ревизия 32, 3 попытки). Теперь берётся кнопка смены тарифа сайта\n(data-metric-name basketMetric:handleClickChangeTariffButton), иначе «изменить» рядом с названием\nтарифа «подписка bee …», иначе первая «изменить». Маркер: TARIFF_CHANGE_BUTTON_1591R33.\n'
# Revision 34: the number of Chromium instances comes from BEELINE_BROWSERS (default 2).
BROWSER_ENV_MARKER = "BROWSER_COUNT_ENV_1591R34"
OLD_BROWSER_COUNT_R34 = 'BROWSER_COUNT = 2  # TWO_BROWSERS_1591R28: two Chromium instances, TABS_PER_BROWSER tabs each\n'
NEW_BROWSER_COUNT_R34 = '# BROWSER_COUNT_ENV_1591R34: BEELINE_BROWSERS=1 in the systemd unit runs one Chromium on a small\n# server (4 vCPU / 8 GB ran two at load average 20: every click and wait timed out). Default 2 (r28).\ndef _browser_count_1591r34(default=2):\n    try:\n        value = int(str(os.environ.get("BEELINE_BROWSERS") or default).strip())\n    except ValueError:\n        value = default\n    return min(max(value, 1), 4)\n\n\nBROWSER_COUNT = _browser_count_1591r34()  # TWO_BROWSERS_1591R28: Chromium instances, TABS_PER_BROWSER tabs each\n'
README_NOTE_R34 = '\n\nРЕВИЗИЯ 34 (fix_package_1591.py)\nЧисло Chromium задаётся переменной окружения BEELINE_BROWSERS (по умолчанию 2, как в ревизии 28;\nдопустимо 1–4), вкладок по-прежнему 4 на браузер. На сервере 4 vCPU / 8 ГБ два Chromium дали load\naverage 20 и нехватку памяти: клики и ожидания не укладывались в таймауты, строки падали на тарифе.\nТам ставится 1: drop-in /etc/systemd/system/beeline.service.d/browsers.conf с\n[Service] Environment=BEELINE_BROWSERS=1, затем systemctl daemon-reload и restart.\nМаркер: BROWSER_COUNT_ENV_1591R34.\n'
# Revision 35: the sign trace in Telegram is one line; the jsonl record keeps the full trace.
TRACE_COMPACT_MARKER = "TRACE_COMPACT_1591R35"
OLD_TRACE_LINES_R35 = 'def _sign_trace_lines_1591r25(summary):\n    if not summary:\n        return []\n    out = [f"Подпись: {summary.get(\'url_before\') or \'—\'} → {summary.get(\'url_after\') or \'—\'}"]\n    for r in (summary.get("responses") or [])[:6]:\n        line = f"  {r.get(\'method\')} {r.get(\'url\')} → {r.get(\'status\')}"\n        if r.get("body"):\n            line += " " + str(r["body"])[:160]\n        out.append(line)\n    for f in (summary.get("failed") or [])[:3]:\n        out.append(f"  сеть: {f.get(\'url\')} — {f.get(\'error\')}")\n    for c in (summary.get("console") or [])[:3]:\n        out.append(f"  console {c.get(\'type\')}: {c.get(\'text\')}")\n    return out\n'
NEW_TRACE_LINES_R35 = 'def _sign_trace_lines_1591r25(summary):\n    """TRACE_COMPACT_1591R35: one line in Telegram (the full trace stays in the jsonl record and\n    the journal); HTTP errors, network failures and console errors are still listed."""\n    if not summary:\n        return []\n    responses = summary.get("responses") or []\n\n    def _status(response):\n        try:\n            return int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            return 0\n\n    signed = [r for r in responses if "checksignature" in str(r.get("url") or "").lower()]\n    passport = [r for r in responses if "sendpassportdata" in str(r.get("url") or "").lower()]\n    parts = []\n    if signed:\n        parts.append(f"подпись → {_status(signed[-1])}")\n    if passport:\n        parts.append(f"паспортные данные → {_status(passport[-1])}")\n    if not parts:\n        parts.append("запрос подписи в сети не замечен" if not responses else f"ответов {len(responses)}")\n    out = ["Подпись (сеть): " + ", ".join(parts)]\n    for r in [r for r in responses if _status(r) >= 400][:3]:\n        line = f"  {r.get(\'method\')} {r.get(\'url\')} → {r.get(\'status\')}"\n        if r.get("body"):\n            line += " " + str(r["body"])[:160]\n        out.append(line)\n    for f in (summary.get("failed") or [])[:3]:\n        out.append(f"  сеть: {f.get(\'url\')} — {f.get(\'error\')}")\n    for c in (summary.get("console") or [])[:3]:\n        out.append(f"  console {c.get(\'type\')}: {c.get(\'text\')}")\n    return out\n'
README_NOTE_R35 = '\n\nРЕВИЗИЯ 35 (fix_package_1591.py)\nСообщения #оплата и #неподтверждено без сетевого следа подписи ревизии 25 построчно: вместо списка\nзапросов одна строка «Подпись (сеть): подпись → 200, паспортные данные → 202». Ошибки HTTP (>= 400),\nсбои сети и ошибки console по-прежнему перечисляются. Полный след остаётся в записи jsonl и в\nжурнале. Маркер: TRACE_COMPACT_1591R35.\n'
# Revision 36: the pushed hash_order link belongs to the current row, never to an earlier one of the tab.
SIM_URL_MARKER = "SIM_URL_PER_ROW_1591R36"
OLD_PENDING_URL_R36 = '        cached_url = getattr(page, "_reserved_sim_url", None)\n        cached_number = getattr(page, "_reserved_sim_number", None)\n        if cached_url and not worker.get("reserved_sim_url"):\n            worker["reserved_sim_url"] = cached_url\n'
NEW_PENDING_URL_R36 = '        cached_url = getattr(page, "_reserved_sim_url", None)\n        cached_number = getattr(page, "_reserved_sim_number", None)\n        # SIM_URL_PER_ROW_1591R36: the offer URL captured for THIS row (locked by\n        # capture_esim_offer_page) replaces whatever the worker remembered; the old rule\n        # "only when empty" kept the first row\'s link for every later row of the tab.\n        if cached_url and (getattr(page, "_reserved_sim_url_locked", False) or not worker.get("reserved_sim_url")):\n            worker["reserved_sim_url"] = cached_url\n'
OLD_RESET_STATE_R36 = '    worker["diagnostic"] = None\n    worker["post_retry_deadline"] = None\n'
NEW_RESET_STATE_R36 = '    worker["diagnostic"] = None\n    worker["reserved_sim_url"] = None     # SIM_URL_PER_ROW_1591R36: a row never inherits the\n    worker["reserved_sim_number"] = None  # previous row\'s order link or reserved number\n    worker["post_retry_deadline"] = None\n'
README_NOTE_R36 = '\n\nРЕВИЗИЯ 36 (fix_package_1591.py)\nСсылка eSIM в пуше принадлежала не той строке. Ссылка заказа (hash_order) копировалась в память\nвкладки только когда там пусто, а между строками память не очищалась: первая строка вкладки\nполучала свою ссылку, все следующие — ссылку первой (номер eSIM при этом перезаписывался и был\nверным). По такой ссылке сайт показывал чужой заказ без данных («введите данные заново»). Теперь\nссылка берётся из захвата текущей строки (замок capture_esim_offer_page), а reset_runtime_state\nочищает ссылку и номер между строками. Команда Telegram /res <номер eSIM из пуша или номер строки>\nотвечает ссылкой заказа, который реально подписан в этой строке (по журналу за 3 дня).\nМаркер: SIM_URL_PER_ROW_1591R36.\n'
OLD_CTRL_IMPORT_R36 = 'import os\nimport signal\n'
NEW_CTRL_IMPORT_R36 = 'import os\nimport re\nimport signal\n'
OLD_CTRL_RESTART_BRANCH_R36 = '                    if text.startswith("/restart"):  # SCHEDULED_RESTART_1591R13\n                        waiting_upload = False\n                        _send(_restart_command(text[len("/restart"):]))\n                        continue\n'
NEW_CTRL_RESTART_BRANCH_R36 = '                    if text.startswith("/restart"):  # SCHEDULED_RESTART_1591R13\n                        waiting_upload = False\n                        _send(_restart_command(text[len("/restart"):]))\n                        continue\n\n                    if text.startswith("/res"):  # SIM_URL_PER_ROW_1591R36: the row\'s real order link\n                        waiting_upload = False\n                        _send(_row_link_command(text[len("/res"):]))\n                        continue\n'
OLD_CTRL_RELAUNCH_DEF_R36 = 'def _restart_after_drain(proc):\n'
NEW_CTRL_ROWLINK_R36 = '# SIM_URL_PER_ROW_1591R36\n_RL_LINE = re.compile(r"^(?P<ts>\\S+)\\s+\\S+\\s+python\\[(?P<pid>\\d+)\\]:\\s?(?P<msg>.*)$")\n_RL_START = re.compile(r"\\[Вкладка (?P<tab>\\d+)\\] Обрабатываю строку (?P<row>\\d+), номер заканчивается на (?P<tail>\\d+)")\n_RL_OFFER = re.compile(r"eSIM offer сохранён: номер=(?P<num>\\S+) \\| (?P<url>\\S+hash_order=[0-9a-f]+)")\n_RL_OUTCOMES = (\n    ("оплата", re.compile(r"ТРЕБУЕТСЯ ОПЛАТА\\. Строка (?P<row>\\d+)")),\n    ("не подтверждена", re.compile(r"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\\. Строка (?P<row>\\d+)")),\n    ("результат", re.compile(r"Результат строки (?P<row>\\d+): (?P<status>\\S+)")),\n)\n\n\ndef _rows_from_journal_1591r36(log):\n    """Rows as the journal saw them: start line, every «продолжить» offer capture, outcome."""\n    rows, current = [], {}\n    for line in log.splitlines():\n        m = _RL_LINE.match(line)\n        if not m:\n            continue\n        ts, pid, msg = m.group("ts")[:19].replace("T", " "), m.group("pid"), m.group("msg")\n        s = _RL_START.search(msg)\n        if s:\n            info = {"row": s.group("row"), "tab": s.group("tab"), "tail": s.group("tail"), "start": ts,\n                    "offers": [], "signed": False, "outcome": ""}\n            rows.append(info)\n            current[pid] = info\n            continue\n        info = current.get(pid)\n        if info is None:\n            continue\n        o = _RL_OFFER.search(msg)\n        if o:\n            info["offers"].append((ts, o.group("num"), o.group("url")))\n            continue\n        if "Нажата кнопка «Подписать договор»" in msg:\n            info["signed"] = True\n            continue\n        for name, pat in _RL_OUTCOMES:\n            r = pat.search(msg)\n            if r and r.group("row") == info["row"]:\n                info["outcome"] = name if name != "результат" else r.group("status")\n                break\n    return rows\n\n\ndef _row_link_command(argument):\n    """/res <номер eSIM из пуша, хотя бы 4 последние цифры> или /res <номер строки>.\n\n    Before revision 36 the push could carry the link of the tab\'s earlier row; the journal\n    keeps the real one: the last offer captured for the row is the order that was signed."""\n    key = re.sub(r"\\D", "", argument or "")\n    if len(key) < 3:\n        return ("Формат: /res <номер eSIM из пуша> (можно последние 4–6 цифр) или /res <номер строки>. "\n                "Отвечу ссылкой заказа, который реально подписан в этой строке.")\n    try:\n        log = subprocess.run(["journalctl", "-u", "beeline", "--no-pager", "-o", "short-iso", "--since", "-3 days"],\n                             capture_output=True, text=True, timeout=120).stdout\n    except Exception as exc:\n        return f"Журнал недоступен: {type(exc).__name__}: {exc}"\n    rows = _rows_from_journal_1591r36(log)\n    by_row = [r for r in rows if r["row"] == key] if len(key) <= 5 else []\n    by_number = [r for r in rows if any(re.sub(r"\\D", "", num).endswith(key) for _, num, _ in r["offers"])\n                 or r["tail"] == key]\n    hits = (by_row + [r for r in by_number if r not in by_row])[-5:]\n    if not hits:\n        return f"В журнале за 3 дня нет строки или номера eSIM, оканчивающегося на …{key[-6:]}."\n    out = []\n    for r in hits:\n        outcome = r["outcome"] or ("подписана" if r["signed"] else "не завершена")\n        head = f"Строка {r[\'row\']} (вкладка {r[\'tab\']}, …{r[\'tail\']}, {r[\'start\'][5:16]}), исход: {outcome}"\n        if not r["offers"]:\n            out.append(head + "\\nСсылка в журнале не найдена.")\n            continue\n        ts, num, url = r["offers"][-1]\n        text = head + f"\\neSIM {num}\\nСсылка заказа: {url}"\n        if len(r["offers"]) > 1:\n            text += f"\\n(ранних заказов этой строки без данных: {len(r[\'offers\']) - 1})"\n        out.append(text)\n    return "\\n\\n".join(out)\n\n\ndef _restart_after_drain(proc):\n'
OLD_TEST_CTRL_NS_R36 = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}','_restart_after_drain':lambda p:False,\n"
NEW_TEST_CTRL_NS_R36 = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}','_restart_after_drain':lambda p:False,'_row_link_command':lambda a:'',\n"
# Revision 37: DeepSeek is asked for help only when the signature did not go through.
AI_SIGN_FAIL_MARKER = "AI_ON_SIGN_FAIL_1591R37"
OLD_GUARD_ASSIST_R37 = '    publish_worker_phase(worker, "POST_AUTH_REVIEW", note)\n    queue_success_assist(worker, note, force=True)\n'
NEW_GUARD_ASSIST_R37 = '    publish_worker_phase(worker, "POST_AUTH_REVIEW", note)\n    # AI_ON_SIGN_FAIL_1591R37: DeepSeek is no longer summoned on every confirmed row. The runtime\n    # signs by itself; DeepSeek is asked only when the signature does not go through (disabled\n    # button, missing region, signing error, request not seen in the network, error page,\n    # unverified page). The push with the network trace is the report for the rest.\n    print(\n        f"[Вкладка {worker[\'id\']}] DeepSeek на подпись не вызываю: runtime подписывает сам; "\n        "вызов только при сбое подписи.",\n        flush=True,\n    )\n'
OLD_AFTER_CLICK_R37 = '            external_heartbeat(worker, "signature_submitted_success_guard")\n            queue_success_assist(worker, "подпись отправлена; наблюдай результат")\n            return\n'
NEW_AFTER_CLICK_R37 = '            external_heartbeat(worker, "signature_submitted_success_guard")\n            if _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n                print(\n                    f"[Вкладка {worker[\'id\']}] Запрос подписи ушёл и принят сайтом (след сети); "\n                    "DeepSeek не вызываю.",\n                    flush=True,\n                )\n            else:\n                queue_success_assist(\n                    worker,\n                    "подпись нажата, но запроса подписи в сети не видно; проверь ошибки/обязательные поля",\n                    force=True,\n                )\n            return\n'
OLD_GUARD_DEF_R37 = 'def enter_success_guard(worker, note):\n'
NEW_GUARD_DEF_R37 = '# AI_ON_SIGN_FAIL_1591R37\nSIGN_OK_RE_1591R37 = re.compile(r"checksignature|/sign\\b", re.I)\n\n\ndef _sign_went_through_1591r37(worker):\n    """True when the trace of the sign click (revision 25) holds a successful answer (status\n    2xx/3xx) to the signing request: the site accepted the signature, DeepSeek is not needed."""\n    trace = (worker or {}).get("sign_trace") or {}\n    for response in trace.get("responses") or []:\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if SIGN_OK_RE_1591R37.search(str(response.get("url") or "")) and 200 <= status < 400:\n            return True\n    return False\n\n\ndef enter_success_guard(worker, note):\n'
README_NOTE_R37 = '\n\nРЕВИЗИЯ 37 (fix_package_1591.py)\nDeepSeek только при сбое подписи. Раньше SUCCESS_ASSIST ставился на каждую строку, прошедшую\nподтверждение (enter_success_guard), и ещё раз после клика «Подписать договор»; на успешных строках\nэто были запросы со скриншотами и отчёт в 2–4 сообщения Telegram впустую. Теперь при входе в\npost-auth DeepSeek не вызывается, а после клика — только если в следе сети (ревизия 25) нет\nуспешного ответа на запрос подписи (_sign_went_through_1591r37). Вызовы при неактивной кнопке,\nотсутствующей области, ошибке подписи, странице ошибки, оставшейся кнопке и неподтверждённой\nстранице сохранены. registration/error после клика записывается как #неподтверждено сразу, без DeepSeek\n(дописывать там нечего); принятый сайтом запрос подписи (2xx) считается доказательством подписания в\nsettle_success. Маркер: AI_ON_SIGN_FAIL_1591R37.\n'
OLD_SIGN_ERROR_R37 = '    if _post_auth_error_page(page):\n        worker["phase"] = "SUCCESS_ASSIST"\n        set_tab_status(\n            worker, "🧠",\n            "После подписи сайт показал ошибку — DeepSeek анализирует. Страницу не трогаю."\n        )\n        external_heartbeat(worker, "success_sign_error")\n        queue_success_assist(worker, "ошибка после попытки подписи")\n        return\n'
NEW_SIGN_ERROR_R37 = '    if _post_auth_error_page(page):\n        # AI_ON_SIGN_FAIL_1591R37: registration/error after the click has no field DeepSeek could\n        # fill; the row is recorded as unverified (number not processed, tab kept open) at once.\n        external_heartbeat(worker, "success_sign_error")\n        accepted = _sign_went_through_1591r37(worker)\n        _finish_unverified_1591r24(\n            base_dir, worker,\n            "после «Подписать договор» сайт показал registration/error"\n            + (" (запрос подписи при этом был принят сайтом)" if accepted else ""),\n        )\n        return\n'
OLD_EVIDENCE_R37 = '    evidence = _signed_evidence_1591r24(page) if page is not None else ""\n'
NEW_EVIDENCE_R37 = '    evidence = _signed_evidence_1591r24(page) if page is not None else ""\n    if not evidence and _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n        evidence = "network:signature_accepted"  # the site answered the signing request with 2xx\n'
# A lite package (r37 without r31) already carries the r37 evidence lines inside the settle block
# that the r31 step rewrites; both application orders give the same text.
OLD_SETTLE_PAYMENT_R26_WITH_R37 = OLD_SETTLE_PAYMENT_R26.replace(OLD_EVIDENCE_R37, NEW_EVIDENCE_R37)
NEW_SETTLE_PAYMENT_R30_WITH_R37 = NEW_SETTLE_PAYMENT_R30.replace(OLD_EVIDENCE_R37, NEW_EVIDENCE_R37)
# Revision 38: the inline menu of the bot (telegram_menu.py) replaces the bottom keyboard and the
# eight edited status messages; short success/payment pushes; DeepSeek only via its button.
TELEGRAM_MENU_SOURCE = Path(__file__).resolve().parent / "telegram_menu.py"
TELEGRAM_MENU_MARKER = 'TELEGRAM_MENU_1591R38'
OLD_STATUS_SYNC_R38 = 'def _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at):\n    """Create the missing status messages and push the changed texts, within the limits."""\n    changed = False\n    for i in range(1, TAB_COUNT + 1):\n        if i in mids:\n            continue\n        r, err = _tg_call_1591r27(\n            cfg, "sendMessage",\n            {"chat_id": chat, "text": f"⏳ Вкладка {i}\\nСтатус: запуск...", "disable_web_page_preview": "true"},\n            state,\n        )\n        if r:\n            mids[i] = r["result"]["message_id"]\n            last[i] = ""\n            changed = True\n            print(f"[Telegram] Сообщение вкладки {i} создано.", flush=True)\n        else:\n            if err != "paused":\n                print(f"[Telegram] ОШИБКА отправки вкладки {i}: {err}", flush=True)\n            break\n    if changed:\n        _tg_status_messages_save_1591r27(chat, mids)\n    now = time.time()\n    for i, mid in list(mids.items()):\n        info = status_map.get(str(i))\n        t = str((info or {}).get("text", ""))\n        if not t or t == last.get(i) or now - float(edited_at.get(i) or 0) < TG_STATUS_MIN_EDIT_GAP_1591R27:\n            continue\n        r, err = _tg_call_1591r27(\n            cfg, "editMessageText",\n            {"chat_id": chat, "message_id": mid, "text": t[:4000], "disable_web_page_preview": "true"},\n            state,\n        )\n        edited_at[i] = time.time()\n        if r:\n            last[i] = t\n            continue\n        if err == "paused":\n            break\n        low = str(err).lower()\n        if "message is not modified" in low:\n            last[i] = t\n        elif "not found" in low or "can\'t be edited" in low or "message_id_invalid" in low:\n            mids.pop(i, None)\n            _tg_status_messages_save_1591r27(chat, mids)\n            print(f"[Telegram] Сообщение вкладки {i} исчезло — создам новое.", flush=True)\n        else:\n            print(f"[Telegram] ОШИБКА обновления вкладки {i}: {err}", flush=True)\n'
NEW_STATUS_SYNC_R38 = 'def _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at):\n    """TELEGRAM_MENU_1591R38: the tab statuses go to status_snapshot.json for the bot\'s menu\n    (its «Статус» view edits one panel while it is open). The eight status messages and their\n    background edits of revision 27 are gone, so nothing is sent to Telegram here."""\n    tabs = {}\n    for i in range(1, TAB_COUNT + 1):\n        info = status_map.get(str(i))\n        if info:\n            tabs[str(i)] = {"text": str(info.get("text", ""))[:1500], "time": float(info.get("time") or 0)}\n    key = json.dumps(tabs, ensure_ascii=False, sort_keys=True)\n    if key == last.get("_snapshot"):\n        return\n    last["_snapshot"] = key\n    path = _tg_status_file_1591r27().with_name("status_snapshot.json")\n    try:\n        tmp = path.with_suffix(".tmp")\n        tmp.write_text(json.dumps({"updated": time.time(), "tabs": tabs}, ensure_ascii=False), "utf-8")\n        tmp.replace(path)\n    except Exception as exc:\n        print(f"[Telegram] status_snapshot.json не записан: {type(exc).__name__}: {exc}", flush=True)\n'
OLD_LOGGER_START_R38 = '    # TG_RATE_1591R27: reuse the status messages of the previous run instead of four new ones\n    # per restart; each is verified by an edit and recreated only when Telegram says it is gone.\n    for i, mid in _tg_status_messages_load_1591r27(chat).items():\n        r, err = _tg_call_1591r27(\n            cfg, "editMessageText",\n            {"chat_id": chat, "message_id": mid, "text": f"⏳ Вкладка {i}\\nСтатус: перезапуск...",\n             "disable_web_page_preview": "true"},\n            state,\n        )\n        if r or err == "paused" or "not modified" in str(err or "").lower():\n            mids[i] = mid\n            last[i] = ""\n    _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)\n    if not mids:\n        print(\n            "[Telegram] Статусные сообщения пока не созданы (лимит Telegram) — попробую позже; "\n            "основной сценарий работает.",\n            flush=True,\n        )\n\n'
NEW_LOGGER_START_R38 = '    # TELEGRAM_MENU_1591R38: statuses are written to status_snapshot.json and shown by the\n    # bot\'s menu on request; no status messages are created or edited here any more.\n    print("[Telegram] Статус вкладок пишется в status_snapshot.json; показ — через меню бота.", flush=True)\n    _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)\n\n'
OLD_SUCCESS_MSG_R38 = 'def _success_message(worker, rec):\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
NEW_SUCCESS_MSG_R38 = 'def _pretty_phone_1591r38(value):\n    d = re.sub(r"\\D", "", str(value or ""))\n    if len(d) == 11 and d[0] in "78":\n        return f"+7 {d[1:4]} {d[4:7]}-{d[7:9]}-{d[9:]}"\n    return str(value or "—")\n\n\ndef _short_push_1591r38(worker, rec, tag, outcome):\n    """TELEGRAM_MENU_1591R38: the push is a short card; the full record (profile, links,\n    network trace) is in the bot\'s menu, «Мои eSIM», and in the jsonl files."""\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n    profile = rec.get("profile") or {}\n    lines = [\n        f"🆕 Новая eSIM · {tag}",\n        f"📱 {_pretty_phone_1591r38(rec.get(\'sim_number\'))}",\n        f"👤 {profile.get(\'full_name\') or \'—\'} · 🎂 {profile.get(\'birth_date\') or \'—\'}",\n        f"📄 Строка {row_no}/{worker.get(\'total_rows\') or \'?\'} · {active_value} | {second_value}",\n        outcome,\n    ]\n    if tag == "#оплата" and rec.get("sim_url"):\n        lines.append(f"🔗 {rec[\'sim_url\']}")\n    lines.append("🗂 Карточка и отметки: меню бота → 📱 Мои eSIM")\n    return "\\n".join(lines)\n\n\ndef _success_message(worker, rec):\n    return _short_push_1591r38(worker, rec, "#успешно", "✅ Договор оформлен")  # TELEGRAM_MENU_1591R38\n\n\ndef _success_message_full_1591r17(worker, rec):\n    """The former long push; kept for reference, the menu card renders the same fields."""\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
OLD_PAYMENT_MSG_R38 = 'def _payment_message_1591r26(worker, rec):\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
NEW_PAYMENT_MSG_R38 = 'def _payment_message_1591r26(worker, rec):\n    return _short_push_1591r38(worker, rec, "#оплата", "💳 Подпись принята, нужна оплата картой; номер помечен обработанным")  # TELEGRAM_MENU_1591R38\n\n\ndef _payment_message_full_1591r26(worker, rec):\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
OLD_REC_TIME_R38 = '        "profile":dict(worker.get("success_profile") or {}),\n'
NEW_REC_TIME_R38 = '        "time": time.strftime("%Y-%m-%d %H:%M:%S"),  # TELEGRAM_MENU_1591R38: order in «Мои eSIM»\n        "profile":dict(worker.get("success_profile") or {}),\n'
OLD_C_IMPORT_R38 = 'import test_beeline as app\n'
NEW_C_IMPORT_R38 = 'import test_beeline as app\nimport telegram_menu as _menu_mod  # TELEGRAM_MENU_1591R38\n'
OLD_C_MARKUP_R38 = 'MENU_MARKUP = json.dumps(\n    {\n        "keyboard": [\n            [{"text": BTN_START}, {"text": BTN_STOP}],\n            [{"text": BTN_RESTART}],\n            [{"text": BTN_UPLOAD}],\n        ],\n        "resize_keyboard": True,\n        "is_persistent": True,\n        "input_field_placeholder": "Команда или сообщение DeepSeek",\n    },\n    ensure_ascii=False,\n)\n'
NEW_C_MARKUP_R38 = '# TELEGRAM_MENU_1591R38: the bottom keyboard is gone; every notice removes it once, the\n# inline menu (telegram_menu.py) is the control surface.\nMENU_MARKUP = json.dumps({"remove_keyboard": True})\n'
OLD_C_PROC_R38 = '    proc = AutomationProcess()\n    waiting_upload = False\n'
NEW_C_PROC_R38 = '    proc = AutomationProcess()\n    waiting_upload = False\n    # TELEGRAM_MENU_1591R38: one panel message with inline buttons; the eight status messages\n    # of earlier revisions are retired once.\n    menu = _menu_mod.TelegramMenu(app, BASE_DIR, proc, link_resolver=_row_link_command)\n    try:\n        menu.retire_status_messages(BASE_DIR / "telegram_status_messages.json")\n    except Exception as exc:\n        print(f"[CTRL] старые статусные сообщения не обновлены: {exc}", flush=True)\n'
OLD_C_HELLO_R38 = '    _send(\n        "🎛 Управление софтом\\n\\n"\n        f"Состояние: {proc.status()}\\n"\n        "Кнопки управления обрабатываются локально и НЕ отправляются DeepSeek."\n    )\n'
NEW_C_HELLO_R38 = '    try:\n        menu.show_menu(fresh=True)  # TELEGRAM_MENU_1591R38\n    except Exception as exc:\n        print(f"[CTRL] меню не показано: {exc}", flush=True)\n'
OLD_C_LOOP_R38 = '        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n        proc.reap()\n'
NEW_C_LOOP_R38 = '        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n        proc.reap()\n        try:\n            menu.tick()  # TELEGRAM_MENU_1591R38: live status only while its view is open\n        except Exception as exc:\n            print(f"[CTRL] меню: {exc}", flush=True)\n'
OLD_C_ALLOWED_R38 = '                "allowed_updates": json.dumps(["message"]),\n'
NEW_C_ALLOWED_R38 = '                "allowed_updates": json.dumps(["message", "callback_query"]),  # TELEGRAM_MENU_1591R38\n'
OLD_C_MSG_R38 = '                try:\n                    msg = upd.get("message") or {}\n                    msg_chat = str((msg.get("chat") or {}).get("id") or "")\n'
NEW_C_MSG_R38 = '                try:\n                    callback = upd.get("callback_query")  # TELEGRAM_MENU_1591R38: inline buttons\n                    if callback:\n                        cb_chat = str(((callback.get("message") or {}).get("chat") or {}).get("id") or "")\n                        if cb_chat == chat and menu.handle_callback(callback) == "upload":\n                            waiting_upload = True\n                        continue\n                    msg = upd.get("message") or {}\n                    msg_chat = str((msg.get("chat") or {}).get("id") or "")\n'
OLD_C_START_R38 = '                    if text in {"/start", "/menu"}:\n                        waiting_upload = False\n                        _send(\n                            "🎛 Управление софтом\\n\\n"\n                            f"Состояние: {proc.status()}"\n                        )\n                        continue\n\n                    if text == "/status":\n                        _send(f"Состояние: {proc.status()}")\n                        continue\n'
NEW_C_START_R38 = '                    if text in {"/start", "/menu"}:\n                        waiting_upload = False\n                        menu.show_menu(fresh=True)  # TELEGRAM_MENU_1591R38\n                        continue\n\n                    if text == "/status":\n                        menu.show_menu(fresh=True)\n                        menu.show_status()\n                        continue\n'
OLD_C_UNKNOWN_R38 = '                        _send("Неизвестная команда. Используй кнопки меню.")\n'
NEW_C_UNKNOWN_R38 = '                        menu.show_menu(fresh=True, note="Неизвестная команда — вот меню.")  # TELEGRAM_MENU_1591R38\n'
OLD_C_AI_R38 = '                    if text:\n                        app._ai_db_store_telegram_update(upd, chat)\n                        print(\n                            f"[CTRL→AI] update={update_id}: {text[:120]}",\n                            flush=True,\n                        )\n                        _typing()\n'
NEW_C_AI_R38 = '                    if text:\n                        # TELEGRAM_MENU_1591R38: DeepSeek gets a message only after «Спросить\n                        # DeepSeek»; any other text (a word, a letter, a symbol) opens the menu.\n                        if not menu.text_is_for_ai():\n                            menu.show_menu(fresh=True)\n                            continue\n                        app._ai_db_store_telegram_update(upd, chat)\n                        print(\n                            f"[CTRL→AI] update={update_id}: {text[:120]}",\n                            flush=True,\n                        )\n                        _typing()\n                        menu.ai_sent()\n'
OLD_I_FILES_R38 = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py', 'symbol_matching.py')\n"
NEW_I_FILES_R38 = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py', 'symbol_matching.py', 'telegram_menu.py')\n"
OLD_I_SUPPORT_R38 = "    raw = (package/'operator_runtime_io.py').read_bytes()\n    if digest(raw) != manifest['files']['operator_runtime_io.py']['output_sha256']:\n        raise RuntimeError('Support module checksum failed')\n    result['operator_runtime_io.py'] = raw\n"
NEW_I_SUPPORT_R38 = "    raw = (package/'operator_runtime_io.py').read_bytes()\n    if digest(raw) != manifest['files']['operator_runtime_io.py']['output_sha256']:\n        raise RuntimeError('Support module checksum failed')\n    result['operator_runtime_io.py'] = raw\n    # TELEGRAM_MENU_1591R38: a support module like operator_runtime_io.py (no original on the server).\n    raw = (package/'telegram_menu.py').read_bytes()\n    if digest(raw) != manifest['files']['telegram_menu.py']['output_sha256']:\n        raise RuntimeError('Menu module checksum failed')\n    result['telegram_menu.py'] = raw\n"
OLD_I_IMPORT_R38 = "'import test_beeline as a; import server_controller as c; import symbol_matching as s; '\n"
NEW_I_IMPORT_R38 = "'import test_beeline as a; import server_controller as c; import symbol_matching as s; import telegram_menu as m; '\n"
OLD_I_ASSERT_R38 = '\'assert a._io1591.VERSION == "15.91-io"; assert s.MATCHER_VERSION == "14.1"; print("IMPORT OK")\''
NEW_I_ASSERT_R38 = '\'assert a._io1591.VERSION == "15.91-io"; assert s.MATCHER_VERSION == "14.1"; assert m.MENU_VERSION == "1591r38"; print("IMPORT OK")\''
OLD_T_FIX_R38 = "'operator_runtime_io.py':b'helper','symbol_matching.py':b'new matcher'})\n"
NEW_T_FIX_R38 = "'operator_runtime_io.py':b'helper','symbol_matching.py':b'new matcher','telegram_menu.py':b'menu'})\n"
OLD_T_CTRL_R38 = "'_restart_after_drain':lambda p:False,'_row_link_command':lambda a:'',\n"
NEW_T_CTRL_R38 = "'_restart_after_drain':lambda p:False,'_row_link_command':lambda a:'',\n                '_menu_mod':types.SimpleNamespace(TelegramMenu=lambda *a,**k:types.SimpleNamespace(show_menu=lambda *a,**k:None,show_status=lambda:None,tick=lambda:None,handle_callback=lambda cb:None,text_is_for_ai=lambda:True,ai_sent=lambda:None,retire_status_messages=lambda *a:0)),'BASE_DIR':Path(d),\n"
OLD_T_COMPILE_R38 = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py','symbol_matching.py'):"
NEW_T_COMPILE_R38 = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py','symbol_matching.py','telegram_menu.py'):"
README_NOTE_R38 = '\n\nРЕВИЗИЯ 38 (fix_package_1591.py)\nМеню бота (telegram_menu.py). Одно сообщение-панель с inline-кнопками: 📊 Статус (правится на месте\nтолько пока открыт, сам закрывается через час), 📱 Мои eSIM (последние оформленные eSIM по 10 на\nстраницу, карточка как прежний полный пуш, отметки 🆕/✅/❌, ссылка из журнала), 📜 Логи (события из\nжурнала за 2 дня постранично), 🤖 Спросить DeepSeek (следующее сообщение уходит DeepSeek, кнопка\nотмены), ▶️ ⏹ 🔄 📥 управление. Нижняя клавиатура убрана. Любое сообщение, кроме команд\n(/restart, /res), открывает меню; к DeepSeek попадает только текст после кнопки «Спросить».\nСтатус вкладок пишется runtime в status_snapshot.json, восемь редактируемых статусных сообщений\nревизии 27 отменены (при первом запуске они один раз переправляются на «статус в меню»).\nПуши об успехе и оплате стали короткими: номер eSIM, ФИО, дата рождения, строка и исходные данные,\nисход (для оплаты — ссылка заказа); полная карточка — в «Мои eSIM». Маркер: TELEGRAM_MENU_1591R38.\n'
# Revision 39: a 4xx on the selfreg requests after the click is a rejection; tabs per Chromium from env.
SIGN_REJECTED_MARKER = "SIGN_REJECTED_1591R39"
OLD_WENT_R39 = 'def _sign_went_through_1591r37(worker):\n    """True when the trace of the sign click (revision 25) holds a successful answer (status\n    2xx/3xx) to the signing request: the site accepted the signature, DeepSeek is not needed."""\n    trace = (worker or {}).get("sign_trace") or {}\n    for response in trace.get("responses") or []:\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if SIGN_OK_RE_1591R37.search(str(response.get("url") or "")) and 200 <= status < 400:\n            return True\n    return False\n'
NEW_WENT_R39 = 'def _sign_went_through_1591r37(worker):\n    """True when the site accepted the WHOLE signing step: a 2xx/3xx answer to the signing\n    request and no 4xx/5xx on any selfreg request of the click (SIGN_REJECTED_1591R39: a\n    checksignature 200 followed by sendpassportdata 412 is a rejection, not a success)."""\n    trace = (worker or {}).get("sign_trace") or {}\n    accepted = False\n    for response in trace.get("responses") or []:\n        url = str(response.get("url") or "")\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if SELFREG_RE_1591R39.search(url) and status >= 400:\n            return False\n        if SIGN_OK_RE_1591R37.search(url) and 200 <= status < 400:\n            accepted = True\n    return accepted\n\n\n# SIGN_REJECTED_1591R39\nSELFREG_RE_1591R39 = re.compile(r"esim-selfreg|checksignature|sendpassportdata|/sign\\b", re.I)\n\n\ndef _sign_rejected_1591r39(worker):\n    """The site\'s refusal after the click, as «412 PERSONAL_TOKEN_ERROR», or "" when none:\n    the first 4xx/5xx answer to a selfreg request in the trace of the sign click."""\n    trace = (worker or {}).get("sign_trace") or {}\n    for response in trace.get("responses") or []:\n        url = str(response.get("url") or "")\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if status < 400 or not SELFREG_RE_1591R39.search(url):\n            continue\n        code = ""\n        m = re.search(r\'"codeValue"\\s*:\\s*"([A-Z_0-9]+)"\', str(response.get("body") or ""))\n        if m:\n            code = m.group(1)\n        step = "паспортные данные" if "sendpassportdata" in url.lower() else ("подпись" if SIGN_OK_RE_1591R37.search(url) else url.rsplit("/", 2)[-2][:30])\n        return f"{status} {code}".strip() + f" ({step})"\n    return ""\n'
OLD_SETTLE_HEAD_R39 = '    page = worker.get("page")\n    payment_text = _payment_page_1591r26(page) if page is not None else ""  # PAYMENT_STEP_1591R26\n'
NEW_SETTLE_HEAD_R39 = '    page = worker.get("page")\n    rejected = _sign_rejected_1591r39(worker)  # SIGN_REJECTED_1591R39: the site refused the data\n    if rejected:\n        _finish_unverified_1591r24(base_dir, worker, f"сайт отверг данные после подписи: {rejected}")\n        return False\n    payment_text = _payment_page_1591r26(page) if page is not None else ""  # PAYMENT_STEP_1591R26\n'
OLD_AFTER_R39 = '            if _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n                print(\n                    f"[Вкладка {worker[\'id\']}] Запрос подписи ушёл и принят сайтом (след сети); "\n                    "DeepSeek не вызываю.",\n                    flush=True,\n                )\n            else:\n'
NEW_AFTER_R39 = '            rejected = _sign_rejected_1591r39(worker)  # SIGN_REJECTED_1591R39\n            if rejected:\n                print(\n                    f"[Вкладка {worker[\'id\']}] Сайт отверг данные после подписи ({rejected}); "\n                    "строка не подтверждена, DeepSeek не вызываю.",\n                    flush=True,\n                )\n                _finish_unverified_1591r24(base_dir, worker, f"сайт отверг данные после подписи: {rejected}")\n                return\n            if _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n                print(\n                    f"[Вкладка {worker[\'id\']}] Запрос подписи ушёл и принят сайтом (след сети); "\n                    "DeepSeek не вызываю.",\n                    flush=True,\n                )\n            else:\n'
OLD_ERR_R39 = '        accepted = _sign_went_through_1591r37(worker)\n        _finish_unverified_1591r24(\n            base_dir, worker,\n            "после «Подписать договор» сайт показал registration/error"\n            + (" (запрос подписи при этом был принят сайтом)" if accepted else ""),\n        )\n'
NEW_ERR_R39 = '        rejected = _sign_rejected_1591r39(worker)  # SIGN_REJECTED_1591R39\n        accepted = _sign_went_through_1591r37(worker)\n        _finish_unverified_1591r24(\n            base_dir, worker,\n            "после «Подписать договор» сайт показал registration/error"\n            + (f": {rejected}" if rejected else (" (запрос подписи при этом был принят сайтом)" if accepted else "")),\n        )\n'
OLD_TABS_R39 = 'TABS_PER_BROWSER = 4  # SUCCESS_TAG_1591R17: four worker tabs\n'
NEW_TABS_R39 = '# SIGN_REJECTED_1591R39: BEELINE_TABS_PER_BROWSER=1 with BEELINE_BROWSERS=8 gives every tab its\n# own Chromium (own cookies, basket and mobile-id token: tabs of one Chromium overwrote each\n# other\'s personal token, 412 PERSONAL_TOKEN_ERROR on the passport data). Default 4 (r17).\ndef _tabs_per_browser_1591r39(default=4):\n    try:\n        value = int(str(os.environ.get("BEELINE_TABS_PER_BROWSER") or default).strip())\n    except ValueError:\n        value = default\n    return min(max(value, 1), 4)\n\n\nTABS_PER_BROWSER = _tabs_per_browser_1591r39()  # SUCCESS_TAG_1591R17: worker tabs per Chromium\n'
README_NOTE_R39 = '\n\nРЕВИЗИЯ 39 (fix_package_1591.py)\n(а) Отказ сайта после подписи. Вкладки одного Chromium делят cookies и localStorage, и персональный\nтокен mobile-id одной вкладки перезаписывался запросом SMS соседней: подпись принималась\n(checksignature 200), а паспортные данные отвергались (sendpassportdata 412 PERSONAL_TOKEN_ERROR).\nКод считал такую строку подписанной по одному checksignature 200. Теперь подпись принята только\nбез 4xx/5xx на запросах selfreg; при отказе строка сразу записывается как #неподтверждено с кодом\nсайта (без DeepSeek и без трёх минут ожидания), номер не помечается обработанным.\n(б) BEELINE_TABS_PER_BROWSER (1–4, по умолчанию 4): с BEELINE_BROWSERS=8 и\nBEELINE_TABS_PER_BROWSER=1 у каждой вкладки свой Chromium, как при ручном оформлении.\nМаркер: SIGN_REJECTED_1591R39.\n'
# Revision 40: an own browser context per worker tab inside the shared Chromium.
ISOLATED_CONTEXT_MARKER = "ISOLATED_CONTEXT_1591R40"
OLD_TAB_CONTEXT_R40 = '        browser = p.chromium.connect_over_cdp(cdp_url)\n        if not browser.contexts:\n            raise RuntimeError("Chromium не вернул общий контекст через CDP.")\n\n        context = browser.contexts[0]\n        page = context.new_page()\n'
NEW_TAB_CONTEXT_R40 = '        browser = p.chromium.connect_over_cdp(cdp_url)\n        if not browser.contexts:\n            raise RuntimeError("Chromium не вернул общий контекст через CDP.")\n\n        # ISOLATED_CONTEXT_1591R40: every worker gets its own browser context inside the shared\n        # Chromium: own cookies, localStorage, basket and mobile-id personal token, like a\n        # separate browser at the memory cost of one tab (tabs of one context overwrote each\n        # other\'s token: 412 PERSONAL_TOKEN_ERROR). Chromium disposes the context when this\n        # process ends; the parent still sees and closes its pages over CDP.\n        context = _isolated_context_1591r40(browser, tab_id)\n        page = context.new_page()\n'
OLD_TAB_DEF_R40 = 'def _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None, captcha_gate=None):  # TWO_BROWSERS_1591R28\n'
NEW_TAB_DEF_R40 = '# ISOLATED_CONTEXT_1591R40\nISOLATED_CONTEXTS = str(os.environ.get("BEELINE_ISOLATED_CONTEXTS") or "1").strip().lower() not in {"0", "off", "no", "false"}\n\n\ndef _isolated_context_1591r40(browser, tab_id):\n    """A browser context of this worker\'s own (no viewport emulation: the real window size, as\n    the shared context had); the shared context when disabled or when Chromium refuses."""\n    if not ISOLATED_CONTEXTS:\n        return browser.contexts[0]\n    try:\n        context = browser.new_context(no_viewport=True)\n        print(f"[Вкладка {tab_id}] Отдельный контекст браузера создан (свои cookies и хранилище).", flush=True)\n        return context\n    except Exception as exc:\n        print(\n            f"[Вкладка {tab_id}] Отдельный контекст не создан ({type(exc).__name__}: {exc}); "\n            "работаю в общем контексте.",\n            flush=True,\n        )\n        return browser.contexts[0]\n\n\ndef _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None, captcha_gate=None):  # TWO_BROWSERS_1591R28\n'
README_NOTE_R40 = '\n\nРЕВИЗИЯ 40 (fix_package_1591.py)\nСвой контекст браузера каждой вкладке внутри общего Chromium (browser.new_context через CDP):\nсвои cookies, localStorage, корзина и персональный токен mobile-id, как у отдельного браузера, а по\nпамяти как одна вкладка. Закрывает перезапись токена соседней вкладкой (412 PERSONAL_TOKEN_ERROR,\nревизия 39) и общую корзину (ревизии 32–33) без восьми Chromium. Chromium удаляет контекст, когда\nпроцесс вкладки завершается, поэтому вкладка успеха/оплаты не остаётся открытой после завершения\nworker (снимки blackbox и записи jsonl сохраняются). Выключить: BEELINE_ISOLATED_CONTEXTS=0.\nМаркер: ISOLATED_CONTEXT_1591R40.\n'
OLD_TEST_TAB_NS_R40 = "                'capture_blackbox':lambda *a:(_ for _ in ()).throw(AssertionError('unexpected phase'))}\n            extract({'_tab_process'},ns)\n"
NEW_TEST_TAB_NS_R40 = "                'capture_blackbox':lambda *a:(_ for _ in ()).throw(AssertionError('unexpected phase')),\n                '_isolated_context_1591r40':lambda b,t:b.contexts[0]}  # ISOLATED_CONTEXT_1591R40\n            extract({'_tab_process'},ns)\n"
# Revision 41: the tariff from the environment; a tariff configurator is confirmed with its defaults.
TARIFF_CONFIG_MARKER = "TARIFF_CONFIG_1591R41"
OLD_TARIFF_NAME_R41 = 'TARIFF_NAME = "подписка bee START"\n'
NEW_TARIFF_NAME_R41 = '# TARIFF_CONFIG_1591R41: BEELINE_TARIFF in the systemd unit picks another card of the picker\n# («для смарт часов», «подписка bee HIT»…), spelled exactly as on the site; default bee START.\nTARIFF_NAME = (os.environ.get("BEELINE_TARIFF") or "").strip() or "подписка bee START"\n'
OLD_CHOOSE_BREAK_R41 = '            if choose_clicked:\n                break\n\n            print(\n                f"После «выбрать» переход пока не подтверждён "\n'
NEW_CHOOSE_BREAK_R41 = '            if choose_clicked and page.locator(\'input#esim[name="sim"]\').count() == 0:\n                # TARIFF_CONFIG_1591R41: some tariffs open a configurator (GB, minutes, options)\n                # after the card\'s «выбрать»; confirm it with the defaults.\n                _confirm_tariff_configurator_1591r41(page, diagnostic)\n            if choose_clicked:\n                break\n\n            print(\n                f"После «выбрать» переход пока не подтверждён "\n'
OLD_CARD_DEF_R41 = 'def _tariff_card_button_1591r32(scope):\n'
NEW_CARD_DEF_R41 = '# TARIFF_CONFIG_1591R41\ndef _confirm_tariff_configurator_1591r41(page, diagnostic=None, timeout=8000):\n    """Some tariffs («для смарт часов») open a configurator after the card\'s «выбрать»: GB,\n    minutes, options and one «выбрать» with the price. Confirm it with the defaults; True when\n    the eSIM control appeared afterwards. Tariffs without a configurator (bee START) never get here\n    with a candidate: the picker holds many «выбрать», the basket page none."""\n    candidates = []\n    try:\n        dialogs = page.locator(\'[role="dialog"], [aria-modal="true"]\')\n        for index in range(min(dialogs.count(), 6)):\n            dialog = dialogs.nth(index)\n            try:\n                if not dialog.is_visible():\n                    continue\n                buttons = dialog.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n                if buttons.count() == 1 and buttons.first.is_visible():\n                    candidates.append(buttons.first)\n            except Exception:\n                continue\n    except Exception:\n        pass\n    if not candidates:\n        try:\n            buttons = page.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n            visible = [buttons.nth(i) for i in range(min(buttons.count(), 30)) if buttons.nth(i).is_visible()]\n            if len(visible) == 1:\n                candidates.append(visible[0])\n        except Exception:\n            pass\n    if not candidates:\n        return False\n    print("Тариф с окном параметров: подтверждаю выбор с настройками по умолчанию...", flush=True)\n    if diagnostic is not None:\n        try:\n            diagnostic.write("tariff_configurator_confirm", tariff=TARIFF_NAME)\n        except Exception:\n            pass\n    try:\n        candidates[0].click(timeout=7000, no_wait_after=True)\n    except Exception as exc:\n        print(f"Кнопка подтверждения тарифа не нажалась: {type(exc).__name__}", flush=True)\n        return False\n    try:\n        page.locator(\'input#esim[name="sim"]\').wait_for(state="attached", timeout=timeout)\n        return True\n    except Exception:\n        return False\n\n\ndef _tariff_card_button_1591r32(scope):\n'
OLD_CARD_RULE_R41 = '            if card.get_by_text(_TARIFF_TITLE_RE_1591R32).count() != 1:\n                continue  # a container of several cards (or the basket plus the picker), not a card\n'
NEW_CARD_RULE_R41 = '            if card.get_by_role("button", name=_CHOOSE_BUTTON_RE).count() != 1:\n                continue  # a container of several cards (or the basket plus the picker), not a card (TARIFF_CONFIG_1591R41: any title)\n'
OLD_CHANGE_TITLES_R41 = '        titles = page.get_by_text(_TARIFF_TITLE_RE_1591R32)\n        for index in range(min(titles.count(), 4)):\n'
NEW_CHANGE_TITLES_R41 = '        titles = page.get_by_text(TARIFF_NAME, exact=True)  # TARIFF_CONFIG_1591R41: any tariff name\n        if titles.count() == 0:\n            titles = page.get_by_text(_TARIFF_TITLE_RE_1591R32)\n        for index in range(min(titles.count(), 4)):\n'
README_NOTE_R41 = '\n\nРЕВИЗИЯ 41 (fix_package_1591.py)\nТариф по настройке. BEELINE_TARIFF в окружении службы задаёт карточку окна «выберите тариф» (точно\nкак на сайте: «для смарт часов», «подписка bee HIT»…), по умолчанию «подписка bee START». У части\nтарифов после «выбрать» на карточке открывается окно параметров (гигабайты, минуты, опции) с одной\nкнопкой «выбрать» и ценой: бот подтверждает его с настройками по умолчанию и дальше идёт как обычно.\nПоиск карточки и кнопки «изменить» больше не требует названия вида «подписка bee …».\nМаркер: TARIFF_CONFIG_1591R41.\n'

# Revision 42: the journal names the tariff it really waits for. «На странице найдено название
# bee START» and «Точный текст bee START пока не появился» were literal strings since 15.91 while the
# check itself used TARIFF_NAME; with BEELINE_TARIFF=для смарт часов the journal still said bee START.
# The startup line now prints the tariff and where it came from.
TARIFF_LOG_MARKER = "TARIFF_LOG_1591R42"
OLD_TARIFF_SEEN_R42 = '            print("На странице найдено название bee START. Выбираю eSIM...")\n'
NEW_TARIFF_SEEN_R42 = '            print(f"На странице найдено название «{TARIFF_NAME}». Выбираю eSIM...")  # TARIFF_LOG_1591R42\n'
OLD_TARIFF_WAIT_R42 = '                "Точный текст bee START пока не появился; "\n                "проверяю фактические элементы оформления.",\n'
NEW_TARIFF_WAIT_R42 = '                f"Точный текст «{TARIFF_NAME}» пока не появился; "  # TARIFF_LOG_1591R42\n                "проверяю фактические элементы оформления.",\n'
OLD_TARIFF_START_R42 = '    print(f"Запускаю {BROWSER_COUNT} Chromium и {TAB_COUNT} рабочие вкладки. Общая очередь строк.")  # BROWSER_HANG_1591R18\n'
NEW_TARIFF_START_R42 = OLD_TARIFF_START_R42 + '    print(f"Тариф: «{TARIFF_NAME}»" + (" (BEELINE_TARIFF из окружения службы)" if (os.environ.get("BEELINE_TARIFF") or "").strip() else " (по умолчанию)"), flush=True)  # TARIFF_LOG_1591R42\n'
README_NOTE_R42 = '\n\nРЕВИЗИЯ 42 (fix_package_1591.py)\nЖурнал называет настоящий тариф. Строки «На странице найдено название bee START» и «Точный текст\nbee START пока не появился» были зашиты в код как есть, хотя проверка шла по TARIFF_NAME: при\nBEELINE_TARIFF=для смарт часов журнал всё равно писал про bee START. Теперь в них подставляется\nTARIFF_NAME, а при старте печатается «Тариф: «…» (BEELINE_TARIFF из окружения службы | по умолчанию)».\nМаркер: TARIFF_LOG_1591R42.\n'

# Revision 43: what the basket really holds. After the tariff step the row reads the visible text
# of the page once (no clicks, no waits): the line naming TARIFF_NAME and the price lines (₽). It is
# printed to the journal («Корзина: …»), written to the row's diagnostic, kept on the page object and
# copied into the success/payment/unverified records and the short push (🧾 line). The payment link
# shows no tariff before paying, so this is the only place the tariff of an order is visible.
BASKET_SUMMARY_MARKER = "BASKET_SUMMARY_1591R43"
OLD_BASKET_CALL_R43 = '        else:\n            print("Форма eSIM уже доступна. Продолжаю без ожидания заголовка тарифа...")\n'
NEW_BASKET_CALL_R43 = OLD_BASKET_CALL_R43 + '        _basket_summary_1591r43(page, diagnostic)  # BASKET_SUMMARY_1591R43: what the basket holds\n'
OLD_BASKET_DEF_R43 = '# TARIFF_CONFIG_1591R41\ndef _confirm_tariff_configurator_1591r41(page, diagnostic=None, timeout=8000):\n'
NEW_BASKET_DEF_R43 = '''# BASKET_SUMMARY_1591R43
def _basket_summary_1591r43(page, diagnostic=None):
    """The tariff title and the price lines visible after the tariff step, read once from the
    page text (nothing clicked, nothing awaited). Printed, written to the diagnostic and kept on
    the page object for the success/payment records and the push. None when the page cannot be read."""
    try:
        text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception as exc:
        print(f"Корзина не прочитана: {type(exc).__name__}", flush=True)
        return None
    lines = [" ".join(line.split()) for line in str(text).splitlines()]
    lines = [line for line in lines if line]
    wanted = TARIFF_NAME.lower()
    tariff = next((line[:80] for line in lines if wanted in line.lower()), None)
    prices = [line[:60] for line in lines if "₽" in line][:4]
    others = [line[:60] for line in lines if _TARIFF_TITLE_RE_1591R32.search(line) and wanted not in line.lower()][:3]
    summary = {"tariff": tariff, "prices": prices, "other_titles": others}
    try:
        setattr(page, "_basket_summary_1591r43", summary)
    except Exception:
        pass
    print(
        f"Корзина: {'«' + tariff + '»' if tariff else 'название «' + TARIFF_NAME + '» не видно'}; "
        f"цены: {', '.join(prices) or '—'}" + (f"; другие названия: {', '.join(others)}" if others else ""),
        flush=True,
    )
    if diagnostic is not None:
        try:
            diagnostic.write("basket_summary", **summary)
        except Exception:
            pass
    return summary


''' + OLD_BASKET_DEF_R43
OLD_BASKET_SUCCESS_R43 = '        "profile":dict(worker.get("success_profile") or {}),\n'
NEW_BASKET_SUCCESS_R43 = OLD_BASKET_SUCCESS_R43 + '        "basket": getattr(worker.get("page"), "_basket_summary_1591r43", None),  # BASKET_SUMMARY_1591R43\n'
OLD_BASKET_PAYMENT_R43 = '        "final_links": list(final.get("links") or []), "payment_text": str(payment_text or ""),\n'
NEW_BASKET_PAYMENT_R43 = OLD_BASKET_PAYMENT_R43 + '        "basket": getattr(worker.get("page"), "_basket_summary_1591r43", None),  # BASKET_SUMMARY_1591R43\n'
OLD_BASKET_UNVERIFIED_R43 = '        "final_links": list(final.get("links") or []), "reason": str(reason or ""),\n'
NEW_BASKET_UNVERIFIED_R43 = OLD_BASKET_UNVERIFIED_R43 + '        "basket": getattr(worker.get("page"), "_basket_summary_1591r43", None),  # BASKET_SUMMARY_1591R43\n'
OLD_BASKET_PUSH_R43 = '    if tag == "#оплата" and rec.get("sim_url"):\n'
NEW_BASKET_PUSH_R43 = ('    basket = rec.get("basket") or {}  # BASKET_SUMMARY_1591R43: the tariff as the basket showed it\n'
                       '    if basket.get("tariff") or basket.get("prices"):\n'
                       '        lines.append(f"🧾 {basket.get(\'tariff\') or \'—\'} · {(basket.get(\'prices\') or [\'—\'])[0]}")\n'
                       + OLD_BASKET_PUSH_R43)
README_NOTE_R43 = ('\n\nРЕВИЗИЯ 43 (fix_package_1591.py)\nЧто лежит в корзине. После шага тарифа строка один раз читает видимый текст страницы (ничего не\n'
                   'нажимая и не ожидая): строку с названием TARIFF_NAME и строки с ценой (₽). Это печатается в журнал\n'
                   '(«Корзина: …»), пишется в диагностику строки и попадает в записи успеха/оплаты/неподтверждённой\n'
                   'подписи (поле basket) и в короткий пуш строкой 🧾. Ссылка заказа до оплаты тариф не показывает,\n'
                   'поэтому это единственное место, где тариф заказа виден. Маркер: BASKET_SUMMARY_1591R43.\n')

# Revision 44: honest prices. r43 took the first «₽» line of the whole basket page as the price of
# the chosen tariff (the push said 700 ₽ for a 300 ₽ tariff). Now the price comes from the card
# that holds TARIFF_NAME (its nearest ancestor with a ₽ line); the other prices of the page are kept
# apart. Before the configurator of a tariff («для смарт часов») is confirmed, its text and every
# option (radio/checkbox/tab/button, checked or not) go to the journal and the diagnostic, so the
# set the site preselects (800 ₽ instead of the 300 ₽ base) can be seen and chosen on purpose later.
CONFIGURATOR_DUMP_MARKER = "CONFIGURATOR_DUMP_1591R44"
OLD_BASKET_EVAL_R44 = '''    try:
        text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception as exc:
        print(f"Корзина не прочитана: {type(exc).__name__}", flush=True)
        return None
    lines = [" ".join(line.split()) for line in str(text).splitlines()]
    lines = [line for line in lines if line]
    wanted = TARIFF_NAME.lower()
    tariff = next((line[:80] for line in lines if wanted in line.lower()), None)
    prices = [line[:60] for line in lines if "₽" in line][:4]
    others = [line[:60] for line in lines if _TARIFF_TITLE_RE_1591R32.search(line) and wanted not in line.lower()][:3]
    summary = {"tariff": tariff, "prices": prices, "other_titles": others}
'''
NEW_BASKET_EVAL_R44 = '''    try:
        got = page.evaluate(_BASKET_JS_1591R44, TARIFF_NAME)  # CONFIGURATOR_DUMP_1591R44: the card's own prices
    except Exception as exc:
        print(f"Корзина не прочитана: {type(exc).__name__}", flush=True)
        return None
    if isinstance(got, dict):
        text, card_prices = got.get("text") or "", [str(p)[:60] for p in (got.get("card_prices") or [])][:3]
    else:
        text, card_prices = got or "", []
    lines = [" ".join(line.split()) for line in str(text).splitlines()]
    lines = [line for line in lines if line]
    wanted = TARIFF_NAME.lower()
    norm = lambda s: re.sub(r"[^0-9a-zа-яё]+", "", s.lower())   # «для смарт-часов» == «для смарт часов»
    tariff = next((line[:80] for line in lines if norm(wanted) and norm(wanted) in norm(line)), None)
    page_prices = [line[:60] for line in lines if "₽" in line][:4]
    others = [line[:60] for line in lines if _TARIFF_TITLE_RE_1591R32.search(line) and norm(wanted) not in norm(line)][:3]
    # "prices" are the prices of the tariff's own card (the push shows the first); the rest of the page apart
    summary = {"tariff": tariff, "prices": card_prices, "page_prices": page_prices, "other_titles": others}
'''
OLD_BASKET_PRINT_R44 = '''    print(
        f"Корзина: {'«' + tariff + '»' if tariff else 'название «' + TARIFF_NAME + '» не видно'}; "
        f"цены: {', '.join(prices) or '—'}" + (f"; другие названия: {', '.join(others)}" if others else ""),
        flush=True,
    )
'''
NEW_BASKET_PRINT_R44 = '''    print(
        f"Корзина: {'«' + tariff + '»' if tariff else 'название «' + TARIFF_NAME + '» не видно'}; "
        f"цена карточки: {', '.join(card_prices) or 'не найдена'}; на странице ещё: {', '.join(page_prices) or '—'}"
        + (f"; другие названия: {', '.join(others)}" if others else ""),
        flush=True,
    )
'''
OLD_BASKET_DEF_HEAD_R44 = '# BASKET_SUMMARY_1591R43\ndef _basket_summary_1591r43(page, diagnostic=None):\n'
NEW_BASKET_DEF_HEAD_R44 = '''# CONFIGURATOR_DUMP_1591R44: the page text plus the ₽ lines of the card holding the tariff title
# (the nearest ancestor of the title whose text has a ₽ and is still short enough to be one card).
_BASKET_JS_1591R44 = """(name) => {
  const text = document.body ? document.body.innerText : '';
  const norm = s => String(s || '').toLowerCase().replace(/[^0-9a-zа-яё]+/g, '');   // «смарт-часов» == «смарт часов»
  const wanted = norm(name);
  const out = {text: text, card_prices: []};
  if (!wanted) return out;
  const vis = el => { try { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; } catch (_) { return false; } };
  const owns = el => { let t = ''; for (const n of el.childNodes) if (n.nodeType === 3) t += n.textContent; return norm(t); };
  const titles = [];
  for (const el of document.querySelectorAll('body *')) {
    if (titles.length >= 6) break;
    if (!vis(el)) continue;
    const own = owns(el);
    if (own && own.includes(wanted) && own.length <= wanted.length + 20) titles.push(el);
  }
  for (const title of titles) {
    let node = title;
    for (let depth = 0; depth < 10 && node && node !== document.body; depth++, node = node.parentElement) {
      const t = node.innerText || '';
      if (t.length > 900) break;
      if (t.includes('₽')) {
        const lines = t.split('\\\\n').map(s => s.replace(/\\\\s+/g, ' ').trim()).filter(s => s.includes('₽'));
        if (lines.length) { out.card_prices = lines.slice(0, 3); return out; }
      }
    }
  }
  return out;
}"""

_CONFIGURATOR_JS_1591R44 = """(root) => {
  const scope = root || document.body;
  const vis = el => { try { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; } catch (_) { return false; } };
  const options = [];
  const sel = '[role=radio],[role=checkbox],[role=option],[role=tab],[role=switch],input[type=radio],input[type=checkbox],input[type=range],button,label,[aria-checked],[aria-selected],[aria-pressed]';
  for (const el of scope.querySelectorAll(sel)) {
    if (options.length >= 60 || !vis(el)) continue;
    const label = (el.tagName === 'INPUT' && el.labels && el.labels[0]) ? el.labels[0].innerText : '';
    const text = ((el.innerText || label || el.getAttribute('aria-label') || el.value || '') + '').replace(/\\\\s+/g, ' ').trim().slice(0, 80);
    const state = el.getAttribute('aria-checked') || el.getAttribute('aria-selected') || el.getAttribute('aria-pressed')
      || (el.checked === true ? 'true' : (el.checked === false ? 'false' : ''));
    const cls = (el.className && typeof el.className === 'string') ? el.className.slice(0, 60) : '';
    options.push({tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '', text: text, state: state,
                  value: el.value != null ? String(el.value).slice(0, 20) : '', cls: cls});
  }
  return {text: (scope.innerText || '').slice(0, 2500), options: options};
}"""


# BASKET_SUMMARY_1591R43
def _basket_summary_1591r43(page, diagnostic=None):
'''
OLD_CONFIG_SCOPE_R44 = '''    candidates = []
    try:
        dialogs = page.locator('[role="dialog"], [aria-modal="true"]')
        for index in range(min(dialogs.count(), 6)):
            dialog = dialogs.nth(index)
            try:
                if not dialog.is_visible():
                    continue
                buttons = dialog.get_by_role("button", name=_CHOOSE_BUTTON_RE)
                if buttons.count() == 1 and buttons.first.is_visible():
                    candidates.append(buttons.first)
            except Exception:
                continue
    except Exception:
        pass
'''
NEW_CONFIG_SCOPE_R44 = '''    candidates = []
    scope = None  # CONFIGURATOR_DUMP_1591R44: the dialog that holds the button, for the dump
    try:
        dialogs = page.locator('[role="dialog"], [aria-modal="true"]')
        for index in range(min(dialogs.count(), 6)):
            dialog = dialogs.nth(index)
            try:
                if not dialog.is_visible():
                    continue
                buttons = dialog.get_by_role("button", name=_CHOOSE_BUTTON_RE)
                if buttons.count() == 1 and buttons.first.is_visible():
                    candidates.append(buttons.first)
                    scope = dialog
            except Exception:
                continue
    except Exception:
        pass
'''
OLD_CONFIG_PRINT_R44 = '''    print("Тариф с окном параметров: подтверждаю выбор с настройками по умолчанию...", flush=True)
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_configurator_confirm", tariff=TARIFF_NAME)
        except Exception:
            pass
'''
NEW_CONFIG_PRINT_R44 = '''    print("Тариф с окном параметров: подтверждаю выбор с настройками по умолчанию...", flush=True)
    _dump_configurator_1591r44(page, scope, diagnostic)  # CONFIGURATOR_DUMP_1591R44: what is preselected
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_configurator_confirm", tariff=TARIFF_NAME)
        except Exception:
            pass
'''
OLD_CONFIG_DEF_R44 = '# TARIFF_CONFIG_1591R41\ndef _confirm_tariff_configurator_1591r41(page, diagnostic=None, timeout=8000):\n'
NEW_CONFIG_DEF_R44 = '''# CONFIGURATOR_DUMP_1591R44
def _dump_configurator_1591r44(page, scope=None, diagnostic=None):
    """The configurator as the site shows it before the bot confirms it: its text and every option
    with its state. One journal line (the checked options and the ₽ lines) and the full dump in
    the diagnostic (event tariff_configurator_dump). Read-only; never raises."""
    try:
        handle = scope.element_handle(timeout=2000) if scope is not None else None
        got = page.evaluate(_CONFIGURATOR_JS_1591R44, handle)
    except Exception as exc:
        print(f"Окно параметров тарифа не прочитано: {type(exc).__name__}", flush=True)
        return None
    if not isinstance(got, dict):
        return None
    options = [o for o in (got.get("options") or []) if isinstance(o, dict)]
    text = str(got.get("text") or "")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    prices = [line[:60] for line in lines if "₽" in line][:6]
    checked = [f"{o.get('text') or o.get('value') or o.get('tag')}" for o in options if str(o.get("state")) == "true"][:8]
    print(
        f"Окно параметров тарифа «{TARIFF_NAME}»: вариантов {len(options)}; выбрано: {', '.join(checked) or '—'}; "
        f"цены: {', '.join(prices) or '—'}",
        flush=True,
    )
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_configurator_dump", tariff=TARIFF_NAME, text=text[:2500], options=options[:60])
        except Exception:
            pass
    return {"text": text, "options": options, "prices": prices, "checked": checked}


''' + OLD_CONFIG_DEF_R44
README_NOTE_R44 = ('\n\nРЕВИЗИЯ 44 (fix_package_1591.py)\nЧужой тариф не оформляется: при заданном BEELINE_TARIFF строка, в корзине которой нет этого названия,\n'
                   'перезапускается (RECOVERABLE_RESTART_ROW), а не идёт дальше с тем, что подставил сайт (bee HIT за 800 ₽ уходил как\n'
                   '«для смарт часов»); BEELINE_TARIFF_STRICT=0 отключает. Окно параметров тарифа распознаётся и как панель\n'
                   'по тексту «гигабайты и минуты» с одной кнопкой «выбрать…»; нераспознанное окно пишется в диагностику.\n'
                   'Честные цены. В r43 ценой тарифа считалась первая строка с «₽» на всей странице корзины (пуш писал\n'
                   '700 ₽ для тарифа за 300). Теперь цена берётся из карточки с названием тарифа (ближайший блок вокруг\n'
                   'названия, где есть ₽), остальные цены страницы — отдельно (page_prices). Перед подтверждением окна\n'
                   'параметров тарифа («для смарт часов») его текст и все варианты с состоянием пишутся в журнал\n'
                   '(«Окно параметров тарифа …: выбрано: …; цены: …») и в диагностику (tariff_configurator_dump), чтобы\n'
                   'видеть, какой набор сайт подставляет по умолчанию. Маркер: CONFIGURATOR_DUMP_1591R44.\n')
OLD_BASKET_DIAG_R44 = '            diagnostic.write("basket_summary", **summary)\n'
NEW_BASKET_DIAG_R44 = '            diagnostic.write("basket_summary", text=str(text)[:3000], **summary)  # CONFIGURATOR_DUMP_1591R44: the page as seen\n'

# r44, part two: the row never continues with a basket that lacks the configured tariff, and the
# configurator is recognised by its own text («гигабайты и минуты») when it is not a dialog.
OLD_STRICT_CALL_R44 = '        _basket_summary_1591r43(page, diagnostic)  # BASKET_SUMMARY_1591R43: what the basket holds\n'
NEW_STRICT_CALL_R44 = ('        basket_1591r43 = _basket_summary_1591r43(page, diagnostic)  # BASKET_SUMMARY_1591R43: what the basket holds\n'
                       '        _require_tariff_in_basket_1591r44(basket_1591r43, diagnostic)  # CONFIGURATOR_DUMP_1591R44: not another tariff\n')
OLD_STRICT_DEF_R44 = '# CONFIGURATOR_DUMP_1591R44\ndef _dump_configurator_1591r44(page, scope=None, diagnostic=None):\n'
NEW_STRICT_DEF_R44 = '''# CONFIGURATOR_DUMP_1591R44: with BEELINE_TARIFF set, a basket without that tariff stops the row.
# The site started to prefill the basket with «подписка bee HIT» (800 ₽ start payment); when the
# card's configurator was not recognised the row went on with that basket, because the eSIM form
# was already there. BEELINE_TARIFF_STRICT=0 restores the old behaviour.
TARIFF_STRICT_1591R44 = str(os.environ.get("BEELINE_TARIFF_STRICT") or "1").strip().lower() not in {"0", "off", "no", "false"}


def _require_tariff_in_basket_1591r44(summary, diagnostic=None):
    """RECOVERABLE_RESTART_ROW when the basket summary shows no line with TARIFF_NAME while the
    tariff was set explicitly (BEELINE_TARIFF). An unreadable page is not a verdict."""
    if not TARIFF_STRICT_1591R44 or not (os.environ.get("BEELINE_TARIFF") or "").strip():
        return
    if summary is None or summary.get("tariff"):
        return
    seen = list(summary.get("other_titles") or [])
    print(
        f"В корзине нет тарифа «{TARIFF_NAME}» (видно: {', '.join(seen) or 'ничего похожего'}; "
        f"цены: {', '.join(summary.get('page_prices') or []) or '—'}). Строку с чужим тарифом не оформляю.",
        flush=True,
    )
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_missing_in_basket", tariff=TARIFF_NAME, seen=seen, prices=summary.get("page_prices") or [])
        except Exception:
            pass
    raise RuntimeError(f"RECOVERABLE_RESTART_ROW: в корзине нет тарифа «{TARIFF_NAME}» (видно: {', '.join(seen) or '—'}).")


''' + OLD_STRICT_DEF_R44
OLD_CONFIG_SECOND_R44 = '''    if not candidates:
        try:
            buttons = page.get_by_role("button", name=_CHOOSE_BUTTON_RE)
            visible = [buttons.nth(i) for i in range(min(buttons.count(), 30)) if buttons.nth(i).is_visible()]
            if len(visible) == 1:
                candidates.append(visible[0])
        except Exception:
            pass
    if not candidates:
        return False
'''
NEW_CONFIG_SECOND_R44 = '''    if not candidates:
        # CONFIGURATOR_DUMP_1591R44: the site's configurator is a panel, not a dialog: the block
        # around «гигабайты и минуты» with one button starting with «выбрать» (its price follows).
        try:
            panel = page.get_by_text(_CONFIGURATOR_HEADER_RE_1591R44).first
            if panel.count() > 0 and panel.is_visible():
                box = panel.locator("xpath=ancestor::*[.//button[starts-with(normalize-space(.), 'выбрать')]][1]")
                buttons = box.get_by_role("button", name=_CHOOSE_PREFIX_RE_1591R44)
                visible = [buttons.nth(i) for i in range(min(buttons.count(), 10)) if buttons.nth(i).is_visible()]
                if len(visible) == 1:
                    candidates.append(visible[0])
                    scope = box
        except Exception:
            pass
    if not candidates:
        try:
            buttons = page.get_by_role("button", name=_CHOOSE_BUTTON_RE)
            visible = [buttons.nth(i) for i in range(min(buttons.count(), 30)) if buttons.nth(i).is_visible()]
            if len(visible) == 1:
                candidates.append(visible[0])
        except Exception:
            pass
    if not candidates:
        try:
            header = page.get_by_text(_CONFIGURATOR_HEADER_RE_1591R44).first
            if header.count() > 0 and header.is_visible():   # the panel is there, its button is not recognised
                print("Окно параметров тарифа видно, но его кнопка «выбрать» не распознана; записываю его в диагностику.", flush=True)
                _dump_configurator_1591r44(page, None, diagnostic)
        except Exception:
            pass
        return False
'''
OLD_CONFIG_RE_R44 = '# CONFIGURATOR_DUMP_1591R44\ndef _dump_configurator_1591r44(page, scope=None, diagnostic=None):\n'
NEW_CONFIG_RE_R44 = ('_CONFIGURATOR_HEADER_RE_1591R44 = re.compile(r"^\\s*гигабайты и минуты\\s*$", re.I)  # CONFIGURATOR_DUMP_1591R44\n'
                     '_CHOOSE_PREFIX_RE_1591R44 = re.compile(r"^\\s*выбрать(\\s|$)", re.I)  # «выбрать», «выбрать за 300 ₽»… (no \\b: JS has no Cyrillic word boundary)\n\n\n' + OLD_CONFIG_RE_R44)


# Revision 45: the configurator decides, not the eSIM form. The basket the site prefills (bee HIT)
# already holds an eSIM form, so r41's «confirm the configurator only when the form is absent» never
# ran and the panel stayed open while the row went on. Now the panel is handled whenever it is
# visible after the card's «выбрать»: the minimal set is chosen (smallest GB and minutes, paid
# options off; BEELINE_TARIFF_MINIMAL=0 keeps the site's defaults), and with BEELINE_TARIFF_PRICE
# (e.g. 200) the panel must show that monthly price before «выбрать», else the row restarts.
# The basket line of the journal also shows the tariff block after «изменить».
CONFIGURATOR_SELECT_MARKER = "CONFIGURATOR_SELECT_1591R45"
OLD_CFG_CONDITION_R45 = '''            if choose_clicked and page.locator('input#esim[name="sim"]').count() == 0:
                # TARIFF_CONFIG_1591R41: some tariffs open a configurator (GB, minutes, options)
                # after the card's «выбрать»; confirm it with the defaults.
                _confirm_tariff_configurator_1591r41(page, diagnostic)
'''
NEW_CFG_CONDITION_R45 = '''            if choose_clicked and (page.locator('input#esim[name="sim"]').count() == 0
                                   or _configurator_visible_1591r45(page)):
                # TARIFF_CONFIG_1591R41: some tariffs open a configurator (GB, minutes, options)
                # after the card's «выбрать». CONFIGURATOR_SELECT_1591R45: the prefilled basket already
                # shows an eSIM form, so the visible panel decides, not the form.
                _confirm_tariff_configurator_1591r41(page, diagnostic)
'''
OLD_CFG_CONFIRM_R45 = '''    print("Тариф с окном параметров: подтверждаю выбор с настройками по умолчанию...", flush=True)
    _dump_configurator_1591r44(page, scope, diagnostic)  # CONFIGURATOR_DUMP_1591R44: what is preselected
'''
NEW_CFG_CONFIRM_R45 = '''    print("Тариф с окном параметров: читаю его и выставляю минимальный набор...", flush=True)
    _dump_configurator_1591r44(page, scope, diagnostic)  # CONFIGURATOR_DUMP_1591R44: what is preselected
    _select_configurator_minimum_1591r45(page, scope, diagnostic)  # CONFIGURATOR_SELECT_1591R45: may restart the row
'''
OLD_CFG_DEFS_R45 = '# CONFIGURATOR_DUMP_1591R44\ndef _dump_configurator_1591r44(page, scope=None, diagnostic=None):\n'
NEW_CFG_DEFS_R45 = '''# CONFIGURATOR_SELECT_1591R45
TARIFF_PRICE_1591R45 = (os.environ.get("BEELINE_TARIFF_PRICE") or "").strip()   # «200»: the monthly price the panel must show
TARIFF_MINIMAL_1591R45 = str(os.environ.get("BEELINE_TARIFF_MINIMAL") or "1").strip().lower() not in {"0", "off", "no", "false"}

_SELECT_MIN_JS_1591R45 = """(root) => {
  const scope = root || document.body;
  const vis = el => { try { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; } catch (_) { return false; } };
  const txt = el => ((el && el.innerText) || '').replace(/\\\\s+/g, ' ').trim();
  const active = el => ['aria-checked', 'aria-selected', 'aria-pressed'].some(a => el.getAttribute(a) === 'true')
    || /(^|[\\\\s_-])(active|selected|checked|current)([\\\\s_-]|$)/i.test(typeof el.className === 'string' ? el.className : '');
  const actions = [];
  for (const r of scope.querySelectorAll('input[type=range]')) {           // sliders: to their minimum
    const min = r.min !== '' ? r.min : '0';
    if (String(r.value) === String(min)) continue;
    try {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(r, min);
      r.dispatchEvent(new Event('input', {bubbles: true}));
      r.dispatchEvent(new Event('change', {bubbles: true}));
      actions.push('ползунок→' + min);
    } catch (_) {}
  }
  const chips = [];                                                        // numeric chips: 2 / 10 / 60 / 100
  for (const el of scope.querySelectorAll('button,[role=radio],[role=tab],[role=option],label,li,span,div')) {
    if (!vis(el) || el.children.length > 1 || el.querySelector('input[type=range]')) continue;
    if (/^\\\\d{1,4}$/.test(txt(el))) chips.push(el);
  }
  const groups = new Map();
  for (const el of chips) {
    if (el.parentElement && chips.includes(el.parentElement) && txt(el.parentElement) === txt(el)) continue;
    const key = el.parentElement;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(el);
  }
  for (const els of groups.values()) {
    if (els.length < 2) continue;
    els.sort((a, b) => parseInt(txt(a), 10) - parseInt(txt(b), 10));
    const smallest = els[0];
    const target = smallest.closest('button,[role=radio],[role=tab],[role=option],label') || smallest;
    if (active(target) || active(smallest)) continue;
    target.click();
    actions.push('выбрано ' + txt(smallest));
  }
  for (const sw of scope.querySelectorAll('[role=switch],[role=checkbox],input[type=checkbox]')) {   // paid options off
    const on = sw.getAttribute('aria-checked') === 'true' || sw.checked === true;
    if (!on) continue;
    const row = sw.closest('label,li,[role=listitem],div');
    const rowText = txt(row);
    if (!/₽/.test(rowText) || /бесплатно/i.test(rowText)) continue;
    (sw.tagName === 'INPUT' && sw.labels && sw.labels[0] ? sw.labels[0] : sw).click();
    actions.push('выключено: ' + rowText.slice(0, 40));
  }
  return actions;
}"""


def _configurator_visible_1591r45(page, timeout_ms=3000):
    """True when the configurator panel («гигабайты и минуты») is visible, waiting up to timeout_ms
    for it to render after the card's «выбрать»."""
    deadline = monotonic() + timeout_ms / 1000.0
    while True:
        try:
            header = page.get_by_text(_CONFIGURATOR_HEADER_RE_1591R44).first
            if header.count() > 0 and header.is_visible():
                return True
        except Exception:
            pass
        if monotonic() >= deadline:
            return False
        page.wait_for_timeout(250)


def _configurator_prices_1591r45(dump):
    """The panel's own price lines: bare prices («200 ₽ в месяц», «800 ₽») and the «выбрать…» button
    text, not the per-option prices («мессенджеры 79 ₽/мес»)."""
    lines = [" ".join(line.split()) for line in str((dump or {}).get("text") or "").splitlines()]
    bare = [line[:60] for line in lines if re.match(r"^\\d[\\d\\s]*₽", line)]
    button = [line[:60] for line in lines if re.match(r"^\\s*выбрать\\b.*₽", line, re.I)]
    return (bare + button) or list((dump or {}).get("prices") or [])


def _select_configurator_minimum_1591r45(page, scope=None, diagnostic=None):
    """The minimal set in the configurator and the price check. Raises RECOVERABLE_RESTART_ROW when
    BEELINE_TARIFF_PRICE is set and the panel does not show that price: a wrong set is never confirmed."""
    actions = []
    if TARIFF_MINIMAL_1591R45:
        for _round in range(3):
            try:
                handle = scope.element_handle(timeout=2000) if scope is not None else None
                done = page.evaluate(_SELECT_MIN_JS_1591R45, handle) or []
            except Exception as exc:
                print(f"Минимальный набор в окне параметров не выставлен: {type(exc).__name__}", flush=True)
                done = []
            actions.extend(str(a) for a in done)
            if not done:
                break
            page.wait_for_timeout(700)
    after = _dump_configurator_1591r44(page, scope, diagnostic) or {}
    prices = _configurator_prices_1591r45(after)
    print(f"Окно параметров: действия: {'; '.join(actions) or 'не потребовались'}; цена теперь: {', '.join(prices) or '—'}", flush=True)
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_configurator_selected", actions=actions, prices=prices, checked=after.get("checked"))
        except Exception:
            pass
    want = re.sub(r"\\D", "", TARIFF_PRICE_1591R45)
    if want and not any(re.search(r"(?<!\\d)" + want + r"(?!\\d)", p) for p in prices):
        print(f"Окно параметров показывает не ту цену (ожидалось {want} ₽): {', '.join(prices) or 'цену не видно'}. Строку не оформляю.", flush=True)
        raise RuntimeError(
            f"RECOVERABLE_RESTART_ROW: окно параметров тарифа «{TARIFF_NAME}» показывает {', '.join(prices) or 'цену не видно'}, ожидалось {want} ₽."
        )
    return actions


''' + OLD_CFG_DEFS_R45
OLD_BASKET_SUMMARY_LINE_R45 = '    summary = {"tariff": tariff, "prices": card_prices, "page_prices": page_prices, "other_titles": others}\n'
NEW_BASKET_SUMMARY_LINE_R45 = '''    block = []  # CONFIGURATOR_SELECT_1591R45: the tariff block of the basket, whatever the title is
    for index, line in enumerate(lines):
        if line.lower() == "изменить":
            block = [item[:60] for item in lines[index + 1:index + 4]]
            break
    summary = {"tariff": tariff, "prices": card_prices, "page_prices": page_prices, "other_titles": others, "block": block}
'''
OLD_BASKET_PRINT_LINE_R45 = '''        f"цена карточки: {', '.join(card_prices) or 'не найдена'}; на странице ещё: {', '.join(page_prices) or '—'}"
'''
NEW_BASKET_PRINT_LINE_R45 = '''        f"цена карточки: {', '.join(card_prices) or 'не найдена'}; блок тарифа: {' | '.join(block) or '—'}; "
        f"на странице ещё: {', '.join(page_prices) or '—'}"
'''
OLD_STRICT_SEEN_R45 = '    seen = list(summary.get("other_titles") or [])\n'
NEW_STRICT_SEEN_R45 = '    seen = list(dict.fromkeys(list(summary.get("block") or []) + list(summary.get("other_titles") or [])))  # CONFIGURATOR_SELECT_1591R45\n'
README_NOTE_R45 = ('\n\nРЕВИЗИЯ 45 (fix_package_1591.py)\nОкно параметров решает, а не форма eSIM. В корзине, которую сайт заполняет сам (bee HIT), форма eSIM\n'
                   'уже есть, поэтому проверка окна параметров из r41 («только если формы нет») не запускалась и панель\n'
                   'оставалась открытой, а строка шла дальше. Теперь панель обрабатывается всегда, когда видна после\n'
                   '«выбрать» на карточке: выставляется минимальный набор (наименьшие ГБ и минуты, платные опции\n'
                   'выключаются; BEELINE_TARIFF_MINIMAL=0 оставляет настройки сайта), а при BEELINE_TARIFF_PRICE (например\n'
                   '200) панель должна показать эту цену в месяц, иначе строка перезапускается и ничего не подтверждается.\n'
                   'Строка «Корзина:» журнала показывает блок тарифа после «изменить». Маркер: CONFIGURATOR_SELECT_1591R45.\n')


# Revision 46: a question typed after «Спросить DeepSeek» is an operator order. The tool set DeepSeek
# gets is chosen from the text: the bot's own [AUTO_…] jobs and texts with a command word get the
# live browser tools, anything else only reading. «ставь улицу» matched no command word, so the
# operator answered it had nothing to write with. The controller now prefixes such a question with
# «/op », the explicit operator prefix (live tools; code tools when it asks for a code change;
# the SUCCESS GUARD bans on close/reload/navigate are unchanged), and the command words are wider.
# Also: the configurator dump is printed once, and the price line prefers «… ₽ в месяц» over options.
CONTROLLER_OUTPUT_SHA_R38_R45 = "d561621ddacaa0c4e602a5da75842207a9b76f563f2d26202e75e9e7eeb6012b"  # controller of r38..r45 (menu)
OPERATOR_LIVE_MARKER = "OPERATOR_LIVE_1591R46"
OLD_C_ASK_R46 = '''                        app._ai_db_store_telegram_update(upd, chat)
                        print(
                            f"[CTRL→AI] update={update_id}: {text[:120]}",
'''
NEW_C_ASK_R46 = '''                        if not text.lower().startswith(("/op ", "/operator ", "оператор ")):
                            # OPERATOR_LIVE_1591R46: a question from «Спросить DeepSeek» is an
                            # operator order with the live browser tools, not a read-only chat.
                            upd = dict(upd)
                            upd["message"] = dict(upd.get("message") or {})
                            upd["message"]["text"] = "/op " + text
                        app._ai_db_store_telegram_update(upd, chat)
                        print(
                            f"[CTRL→AI] update={update_id}: {text[:120]}",
'''
OLD_LIVE_WORDS_R46 = '''    triggers = (
        "нажми", "кликни", "введи", "заполни", "напечатай",
'''
NEW_LIVE_WORDS_R46 = '''    triggers = (
        "нажми", "кликни", "введи", "заполни", "напечатай",
        "ставь", "поставь", "впиши", "вписать", "укажи", "выбери", "подпиши",  # OPERATOR_LIVE_1591R46
        "нарисуй", "дорисуй", "допиши", "заполн", "в поле", "исправь на стран",
'''
OLD_DUMP_HEAD_R46 = '''def _dump_configurator_1591r44(page, scope=None, diagnostic=None):
'''
NEW_DUMP_HEAD_R46 = '''def _dump_configurator_1591r44(page, scope=None, diagnostic=None, announce=True):
'''
OLD_DUMP_PRINT_R46 = '''    print(
        f"Окно параметров тарифа «{TARIFF_NAME}»: вариантов {len(options)}; выбрано: {', '.join(checked) or '—'}; "
        f"цены: {', '.join(prices) or '—'}",
        flush=True,
    )
'''
NEW_DUMP_PRINT_R46 = '''    if announce:  # OPERATOR_LIVE_1591R46: the second read (after the selection) is reported by its caller
        print(
            f"Окно параметров тарифа «{TARIFF_NAME}»: вариантов {len(options)}; выбрано: {', '.join(checked) or '—'}; "
            f"цены: {', '.join(prices) or '—'}",
            flush=True,
        )
'''
OLD_AFTER_DUMP_R46 = '''    after = _dump_configurator_1591r44(page, scope, diagnostic) or {}
'''
NEW_AFTER_DUMP_R46 = '''    after = _dump_configurator_1591r44(page, scope, None, announce=False) or {}  # OPERATOR_LIVE_1591R46: one journal line
'''
OLD_BARE_R46 = '''    bare = [line[:60] for line in lines if re.match(r"^\\d[\\d\\s]*₽", line)]
'''
NEW_BARE_R46 = '''    bare = [line[:60] for line in lines if re.match(r"^\\d[\\d\\s]*₽", line)]
    monthly = [line for line in bare if "в месяц" in line.lower()]  # OPERATOR_LIVE_1591R46: the tariff's line, not «60 ₽/мес» of an option
    bare = monthly or [line for line in bare if "/мес" not in line.lower()] or bare
'''
README_NOTE_R46 = ('\n\nРЕВИЗИЯ 46 (fix_package_1591.py)\nВопрос из кнопки «Спросить DeepSeek» — поручение оператору. Набор инструментов DeepSeek выбирается по\n'
                   'тексту: автоматические задания бота и тексты со словом-командой получают живые инструменты браузера\n'
                   '(ввод, клик, JS), остальное — только чтение. «Ставь улицу» слова-команды не содержало, и оператор отвечал,\n'
                   'что писать ему нечем. Теперь контроллер добавляет к такому вопросу префикс «/op » (явная команда\n'
                   'оператору), список слов-команд шире («ставь», «поставь», «впиши», «укажи», «выбери», «подпиши»…);\n'
                   'запреты SUCCESS GUARD на закрытие/перезагрузку вкладок не меняются. Строка «Окно параметров тарифа …»\n'
                   'печатается один раз, в «цена теперь» предпочитается строка «… ₽ в месяц». Маркер: OPERATOR_LIVE_1591R46.\n')


# Revision 47: the operator fills a missing street instead of stopping. The auto SUCCESS_ASSIST job
# and the mission said what to do about a missing city or region, nothing about the street, so the
# operator reported «no street known, will not invent one» and the row stayed on hold. The rule now:
# type common street names into the street field, take the site's first suggestion for this
# settlement (the same for a required district), the row's phone into an empty contact number,
# and only a form the site itself rejects after that goes to the user. The job text also names the
# live tools the operator holds, so it cannot answer that it has none.
STREET_RULE_MARKER = "STREET_RULE_1591R47"
OLD_AUTO_CITY_R47 = '''        "значения не перезаписывай. Для текущего сценария город при отсутствии — Саратов, "
        "область при отсутствии — Саратовская область. "
'''
NEW_AUTO_CITY_R47 = '''        "значения не перезаписывай. Для текущего сценария город при отсутствии — Саратов, "
        "область при отсутствии — Саратовская область. "
        "УЛИЦА (STREET_RULE_1591R47): если поле улицы пустое или помечено ошибкой, НЕ останавливайся и не "
        "спрашивай пользователя — впиши по очереди «Центральная», «Ленина», «Советская», «Школьная», "
        "«Молодёжная» и выбери ПЕРВУЮ подсказку сайта для этого населённого пункта; если подсказок нет "
        "ни на одно из названий, возьми любую подсказку, которую сайт предлагает на одну букву. Район, "
        "если сайт его требует, — так же первой подсказкой. Пустой контактный номер — номер этой строки. "
        "У ТЕБЯ ЕСТЬ ИНСТРУМЕНТЫ browser_fill, browser_type, browser_press, browser_click, browser_evaluate_js — "
        "действуй ими; не пиши, что инструментов ввода нет. Руки опускай только когда сайт сам отверг все "
        "варианты — тогда перечисли их в отчёте. "
'''
OLD_MISSION_CITY_R47 = '''- Для этого сценария: если отсутствует город — поставь «Саратов» и выбери подсказку;
  если отсутствует область — «Саратовская область» и выбери подсказку.
'''
NEW_MISSION_CITY_R47 = '''- Для этого сценария: если отсутствует город — поставь «Саратов» и выбери подсказку;
  если отсутствует область — «Саратовская область» и выбери подсказку.
- Улица (STREET_RULE_1591R47): пустое поле улицы — не причина останавливаться и не вопрос к
  пользователю. Впиши по очереди «Центральная», «Ленина», «Советская», «Школьная», «Молодёжная»
  и выбери ПЕРВУЮ подсказку сайта для этого населённого пункта; нет подсказок ни на одно — возьми
  любую подсказку на одну букву. Район, если он обязателен, — так же первой подсказкой. Пустой
  контактный номер — номер телефона этой строки. Инструменты ввода (browser_fill, browser_type,
  browser_press, browser_click, browser_evaluate_js) у тебя есть всегда в этой задаче.
'''
README_NOTE_R47 = ('\n\nРЕВИЗИЯ 47 (fix_package_1591.py)\nОператор заполняет пустую улицу, а не останавливается. В автоматическом задании и в миссии было\n'
                   'сказано, что делать с пустым городом и областью, но не с улицей: оператор отвечал «улицу не знаю,\n'
                   'случайную не поставлю», и строка висела. Теперь правило: вписывать по очереди «Центральная», «Ленина»,\n'
                   '«Советская», «Школьная», «Молодёжная» и брать первую подсказку сайта для этого населённого пункта (район,\n'
                   'если обязателен, — так же), пустой контактный номер — номер строки; к пользователю уходит только форма,\n'
                   'которую сайт отверг после всех попыток. В задании перечислены инструменты ввода, которыми он располагает.\n'
                   'Маркер: STREET_RULE_1591R47.\n')


# Revision 48: no endless re-signing, and the observer keeps up with many tabs. When the site
# answered the signing request with 200 but the page stayed on personal-data-form, the row saw the
# button again 12 s later and clicked it again, for ever (every click a new checksignature) with
# DeepSeek never asked (r37). Now the click is made at most SIGN_ATTEMPTS_MAX times per row; then
# the row enters the usual unverified hold (DeepSeek once, 3 minutes, UNVERIFIED for the user).
# The DeepSeek lanes' page collection had a fixed 45 s budget: with 28 tabs it never finished, the
# lane was respawned every 45 s and no job was ever answered; the budget now grows with TAB_COUNT.
RESIGN_LIMIT_MARKER = "RESIGN_LIMIT_1591R48"
OLD_RESIGN_SIGN_R48 = '''        try:
            set_tab_status(
                worker, "✍️",
                "Подтверждение успешно. Заполняю подпись и подписываю договор."
            )
'''
NEW_RESIGN_SIGN_R48 = '''        if _sign_attempts_exhausted_1591r48(worker):  # RESIGN_LIMIT_1591R48: no third click
            settle_success_1591r24(base_dir, worker)
            return
        try:
            set_tab_status(
                worker, "✍️",
                "Подтверждение успешно. Заполняю подпись и подписываю договор."
            )
'''
OLD_RESIGN_COUNT_R48 = '            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25\n'
NEW_RESIGN_COUNT_R48 = ('            worker["sign_attempts_1591r48"] = int(worker.get("sign_attempts_1591r48") or 0) + 1  # RESIGN_LIMIT_1591R48\n'
                        '            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25\n')
OLD_RESIGN_DEF_R48 = 'def settle_success_1591r24(base_dir, worker):\n'
NEW_RESIGN_DEF_R48 = '''# RESIGN_LIMIT_1591R48
SIGN_ATTEMPTS_MAX_1591R48 = 2


def _sign_attempts_exhausted_1591r48(worker):
    """True once «Подписать договор» was clicked SIGN_ATTEMPTS_MAX_1591R48 times for this row and
    the page still shows the button: the click is not repeated (each one sends a new checksignature
    to the site); the row goes to the unverified hold instead (DeepSeek once, then UNVERIFIED)."""
    exhausted = int((worker or {}).get("sign_attempts_1591r48") or 0) >= SIGN_ATTEMPTS_MAX_1591R48
    if exhausted and not worker.get("sign_attempts_reported_1591r48"):
        worker["sign_attempts_reported_1591r48"] = True
        print(
            f"[Вкладка {worker.get('id')}] «Подписать договор» нажата {SIGN_ATTEMPTS_MAX_1591R48} раза, страница не "
            "продвинулась; больше не нажимаю, держу вкладку и отдаю на проверку.",
            flush=True,
        )
    return exhausted


def settle_success_1591r24(base_dir, worker):
'''
OLD_RESIGN_RESET_R48 = '    worker["reserved_sim_url"] = None     # SIM_URL_PER_ROW_1591R36: a row never inherits the\n'
NEW_RESIGN_RESET_R48 = ('    worker["sign_attempts_1591r48"] = 0   # RESIGN_LIMIT_1591R48: the click budget is per row\n'
                        '    worker["sign_attempts_reported_1591r48"] = False\n'
                        '    worker["reserved_sim_url"] = None     # SIM_URL_PER_ROW_1591R36: a row never inherits the\n')
OLD_OBSERVER_LIMIT_R48 = '    limit = float(OBSERVER_COLLECT_TIMEOUT_SECONDS if timeout is None else timeout)\n'
NEW_OBSERVER_LIMIT_R48 = ('    # RESIGN_LIMIT_1591R48: the budget grows with the tabs (28 tabs never fit into 45 s, the lane\n'
                          '    # was respawned every 45 s and answered nothing).\n'
                          '    limit = float(timeout) if timeout is not None else max(float(OBSERVER_COLLECT_TIMEOUT_SECONDS), 6.0 * float(globals().get("TAB_COUNT") or 8))\n')
README_NOTE_R48 = ('\n\nРЕВИЗИЯ 48 (fix_package_1591.py)\nВыключатель DeepSeek: BEELINE_AI=0 в окружении службы отключает оператора целиком (автоматические\n'
                   'задания не ставятся, линии простаивают без запросов к API, при старте «DeepSeek: выключен», на вопрос из меню\n'
                   'бот отвечает, что DeepSeek выключен); в экспериментальной сборке он выключен по умолчанию, BEELINE_AI=1 включает.\n'
                   'Сбор страниц для линий DeepSeek имел жёсткие 45 с: при 28 вкладках он не укладывался и линия перезапускалась\n'
                   'каждые 45 с; лимит теперь 6 с на вкладку, не меньше 45. Логика подписания не менялась. Маркер: RESIGN_LIMIT_1591R48.\n')


# r48, part two: the DeepSeek switch. BEELINE_AI=0 (the experiment build's default; production builds
# default to on) switches the operator off entirely: no automatic jobs (a row whose signature is not
# confirmed is held the usual 3 minutes and recorded as unverified for the user), both lanes idle
# without an API call, the startup line says so, a menu question is answered «DeepSeek выключен».
CONTROLLER_OUTPUT_SHA_R46_R47 = "c700c997e758c55001e598e10b0386cd009bc7def04b89ee234aacda704484cd"  # controller of r46..r47 (/op)
OLD_AI_GATE_DEF_R48 = 'def _auto_assist_allowed(worker, kind, force=False):\n'
NEW_AI_GATE_DEF_R48 = ('# RESIGN_LIMIT_1591R48: BEELINE_AI=0 in the systemd unit switches the DeepSeek operator off: no automatic\n'
                       '# jobs, idle lanes, «DeepSeek выключен» to a menu question. Rows that cannot confirm the signature\n'
                       '# go to the user as unverified after the usual hold. AI_DEFAULT is "0" in the experiment build.\n'
                       'AI_DEFAULT_1591R48 = "1"\n'
                       'AI_ENABLED_1591R48 = str(os.environ.get("BEELINE_AI") or AI_DEFAULT_1591R48).strip().lower() not in {"0", "off", "no", "false"}\n\n\n'
                       'def _auto_assist_allowed(worker, kind, force=False):\n')
OLD_AI_GATE_BODY_R48 = '''    now = monotonic()
    try:
        url = str(worker.get("page").url or "")
    except Exception:
        url = ""
    states = worker.setdefault("auto_assist_state", {})
'''
NEW_AI_GATE_BODY_R48 = '''    if not AI_ENABLED_1591R48:
        return False  # RESIGN_LIMIT_1591R48: nothing is asked of DeepSeek
    now = monotonic()
    try:
        url = str(worker.get("page").url or "")
    except Exception:
        url = ""
    states = worker.setdefault("auto_assist_state", {})
'''
OLD_AI_LANE_R48 = '''    last_observe = 0.0

    while not stop_event.is_set():
        _ai_health_touch(ai_health, "idle")
'''
NEW_AI_LANE_R48 = '''    last_observe = 0.0

    if not AI_ENABLED_1591R48:  # RESIGN_LIMIT_1591R48: the lane idles (the supervisor keeps it alive) and never calls the API
        print(f"[AI {lane.upper()}] DeepSeek выключен (BEELINE_AI=0): запросы не отправляются.", flush=True)
        while not stop_event.is_set():
            _ai_health_touch(ai_health, "idle")
            stop_event.wait(5)
        return

    while not stop_event.is_set():
        _ai_health_touch(ai_health, "idle")
'''
OLD_AI_START_R48 = NEW_TARIFF_START_R42[len(OLD_TARIFF_START_R42):]   # the «Тариф: …» startup line of r42
NEW_AI_START_R48 = '    print("DeepSeek: " + ("включён" if AI_ENABLED_1591R48 else "выключен (BEELINE_AI=0)"), flush=True)  # RESIGN_LIMIT_1591R48\n' + OLD_AI_START_R48
OLD_C_AI_OFF_R48 = '''                        if not text.lower().startswith(("/op ", "/operator ", "оператор ")):
'''
NEW_C_AI_OFF_R48 = '''                        if str(os.environ.get("BEELINE_AI") or "1").strip().lower() in {"0", "off", "no", "false"}:
                            _send("🤖 DeepSeek выключен (BEELINE_AI=0 в настройках службы).")  # RESIGN_LIMIT_1591R48
                            continue
                        if not text.lower().startswith(("/op ", "/operator ", "оператор ")):
'''
OLD_TEST_AI_NS_R48 = "            '_ai_db_fail':lambda *a:(_ for _ in ()).throw(AssertionError(a))"
NEW_TEST_AI_NS_R48 = "            'AI_ENABLED_1591R48':True,'_ai_db_fail':lambda *a:(_ for _ in ()).throw(AssertionError(a))"  # RESIGN_LIMIT_1591R48
# the lite build carries the r48 click counter between capture_contract_details and the trace: the
# r31 step (lite → full) must recognise that shape too
OLD_SIGN_CALL_R25_WITH_R48 = OLD_SIGN_CALL_R25.replace(OLD_RESIGN_COUNT_R48, NEW_RESIGN_COUNT_R48)
NEW_SIGN_CALL_R30_WITH_R48 = NEW_SIGN_CALL_R30.replace(OLD_RESIGN_COUNT_R48, NEW_RESIGN_COUNT_R48)
OLD_EXP_AI_DEFAULT = 'AI_DEFAULT_1591R48 = "1"\n'
NEW_EXP_AI_DEFAULT = 'AI_DEFAULT_1591R48 = "0"  # EXPERIMENT_BROWSERS8_1591: DeepSeek off unless BEELINE_AI=1\n'


# Revision 49: an exhausted row is never a success by the network alone. r48 sent a row whose
# «Подписать договор» had been clicked twice to settle_success, where the r37 rule «a 2xx answer to
# the signing request is evidence» turned it into a false #успешно while the button was still on
# the page. For such rows the network shortcut is off: the usual 3-minute hold, then UNVERIFIED
# with the link for the user. The hold status names DeepSeek only when it is on.
EXHAUSTED_UNVERIFIED_MARKER = "EXHAUSTED_UNVERIFIED_1591R49"
OLD_NET_EVIDENCE_R49 = '    if not evidence and _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n'
NEW_NET_EVIDENCE_R49 = ('    # EXHAUSTED_UNVERIFIED_1591R49: a row that used up its sign clicks with the button still on the page\n'
                        '    # is never a success by the network answer alone\n'
                        '    if not evidence and not worker.get("sign_attempts_reported_1591r48") and _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n')
OLD_LIMIT_CONST_R49 = 'SIGN_ATTEMPTS_MAX_1591R48 = 2\n'
NEW_LIMIT_CONST_R49 = ('# EXHAUSTED_UNVERIFIED_1591R49: off by default (r47 behaviour: the click is repeated while the button is\n'
                       '# there); BEELINE_SIGN_ATTEMPTS=2 in the systemd unit switches the limit on.\n'
                       'SIGN_ATTEMPTS_MAX_1591R48 = int(str(os.environ.get("BEELINE_SIGN_ATTEMPTS") or "0").strip() or 0)\n')
OLD_LIMIT_CHECK_R49 = '    exhausted = int((worker or {}).get("sign_attempts_1591r48") or 0) >= SIGN_ATTEMPTS_MAX_1591R48\n'
NEW_LIMIT_CHECK_R49 = '    exhausted = SIGN_ATTEMPTS_MAX_1591R48 > 0 and int((worker or {}).get("sign_attempts_1591r48") or 0) >= SIGN_ATTEMPTS_MAX_1591R48\n'
OLD_HOLD_STATUS_R49 = '            f"Держу вкладку {UNVERIFIED_HOLD_SECONDS // 60} мин, DeepSeek проверяет.",\n'
NEW_HOLD_STATUS_R49 = ('            f"Держу вкладку {UNVERIFIED_HOLD_SECONDS // 60} мин, " + ("DeepSeek проверяет." if AI_ENABLED_1591R48 else "затем отметка «не подтверждено» (DeepSeek выключен)."),  # EXHAUSTED_UNVERIFIED_1591R49\n')
# the r31 step (lite → full) must recognise the settle block in its r49 shape as well
OLD_SETTLE_PAYMENT_R26_WITH_R49 = OLD_SETTLE_PAYMENT_R26_WITH_R37.replace(OLD_NET_EVIDENCE_R49, NEW_NET_EVIDENCE_R49)
NEW_SETTLE_PAYMENT_R30_WITH_R49 = NEW_SETTLE_PAYMENT_R30_WITH_R37.replace(OLD_NET_EVIDENCE_R49, NEW_NET_EVIDENCE_R49)
README_NOTE_R49 = ('\n\nРЕВИЗИЯ 49 (fix_package_1591.py)\nВ статусе удержания «не подтверждено» DeepSeek упоминается только когда он включён. Логика подписания\n'
                   'не менялась. Маркер: EXHAUSTED_UNVERIFIED_1591R49.\n')


# Revision 50: /clear in the bot runs the same base from the start. The worker is stopped,
# processed_numbers.txt and deferred_rows.jsonl are archived (base_archive/) and removed, clients.txt
# stays, and the worker is started again. Results and eSIM records are untouched.
CONTROLLER_OUTPUT_SHA_R48_R49 = "b008baad1551e6574389743c1b2810a39f03e198a5af4c3a823fe4296386c25c"  # controller of r48..r49 (BEELINE_AI)
CLEAR_BASE_MARKER = "CLEAR_BASE_1591R50"
OLD_CLEAR_MARK_R50 = 'PROGRESS_FILE_NAME = "processed_numbers.txt"\n'
NEW_CLEAR_MARK_R50 = ('# CLEAR_BASE_1591R50: /clear in the controller archives and removes processed_numbers.txt and\n'
                      '# deferred_rows.jsonl (base_archive/) and starts the worker again: the same base from the start.\n'
                      'PROGRESS_FILE_NAME = "processed_numbers.txt"\n')
OLD_C_CLEAR_DEF_R50 = 'def _row_link_command(argument):\n'
NEW_C_CLEAR_DEF_R50 = '''# CLEAR_BASE_1591R50
def _clear_base_command(proc):
    """/clear: the same base from the start. The worker is stopped, processed_numbers.txt and
    deferred_rows.jsonl go to base_archive/ and are removed (clients.txt stays), and the worker is
    started again, so every row of the loaded base is processed anew. Results and eSIM records are
    not touched."""
    if not CLIENTS_FILE.exists() or not CLIENTS_FILE.stat().st_size:
        return "❌ База пуста: нечего запускать заново. Загрузи базу («📥 Загрузить базу»)."
    try:
        rows = len(load_clients(CLIENTS_FILE))
    except Exception:
        rows = -1
    was_running = proc.running()
    if was_running:
        proc.stop()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    deferred = BASE_DIR / "deferred_rows.jsonl"
    processed = 0
    try:
        if PROCESSED_FILE.exists():
            processed = sum(1 for line in PROCESSED_FILE.read_text("utf-8", errors="replace").splitlines() if line.strip())
    except Exception:
        processed = -1
    for path, name in ((PROCESSED_FILE, f"processed_numbers_{stamp}.txt"), (deferred, f"deferred_rows_{stamp}.jsonl")):
        try:
            if path.exists() and path.stat().st_size:
                (ARCHIVE_DIR / name).write_bytes(path.read_bytes())
            path.unlink(missing_ok=True)
        except Exception as exc:
            return f"❌ Не очищено: {path.name}: {type(exc).__name__}: {exc}"
    ok, start_msg = proc.start()
    shown_rows = f"{rows} строк" if rows >= 0 else "строки"
    shown_done = f"{processed}" if processed >= 0 else "?"
    head = f"🧹 Отработанные номера очищены ({shown_done}), отложенные строки сброшены. База из {shown_rows} идёт с начала."
    if ok:
        return head + ("\\n🔄 Процесс перезапущен." if was_running else "\\n▶️ Процесс запущен.")
    return head + f"\\n⚠️ Запуск не удался: {start_msg}"


def _row_link_command(argument):
'''

OLD_C_CLEAR_CMD_R50 = '''                    if text.startswith("/res"):  # SIM_URL_PER_ROW_1591R36: the row's real order link
'''
NEW_C_CLEAR_CMD_R50 = '''                    if text.split()[0].lower().split("@")[0] == "/clear":  # CLEAR_BASE_1591R50
                        waiting_upload = False
                        _send(_clear_base_command(proc))
                        continue

                    if text.startswith("/res"):  # SIM_URL_PER_ROW_1591R36: the row's real order link
'''
README_NOTE_R50 = ('\n\nРЕВИЗИЯ 50 (fix_package_1591.py)\nКоманда /clear в боте запускает ту же базу с начала: процесс останавливается, processed_numbers.txt и\n'
                   'deferred_rows.jsonl копируются в base_archive/ и удаляются (clients.txt остаётся), процесс запускается снова,\n'
                   'и все строки загруженной базы проходят заново. Результаты и записи eSIM не трогаются. Маркер: CLEAR_BASE_1591R50.\n')


# Revision 51: the payment step is recognised only by its own heading. The registration start page
# («оформление eSIM / выберите способ регистрации») lists the steps «подтвердите данные → оплатите
# картой → дождитесь регистрации договора» next to the button «выбрать способ регистрации»; the
# needles «оплатите картой» and «дождитесь регистрации договора» matched that list and a tab standing
# on the start page was pushed as #оплата with an order that had no registration at all (row 22, tab
# 10, 22:29). Now the real screen («теперь пора оплатить eSIM») is required and a page that offers
# a registration method never counts.
PAYMENT_STRICT_MARKER = "PAYMENT_STRICT_1591R51"
OLD_PAYMENT_LOW_R51 = '    low = body.lower()\n    for needle in PAYMENT_NEEDLES_1591R26:\n'
NEW_PAYMENT_LOW_R51 = ('    low = body.lower()\n'
                       '    # PAYMENT_STRICT_1591R51: the registration start page lists the steps («подтвердите данные → оплатите\n'
                       '    # картой → дождитесь регистрации договора») next to «выбрать способ регистрации»; only the real payment\n'
                       '    # screen («теперь пора оплатить eSIM») counts.\n'
                       '    if "способ регистрации" in low or "пора оплатить" not in low:\n'
                       '        return ""\n'
                       '    for needle in PAYMENT_NEEDLES_1591R26:\n')
README_NOTE_R51 = ('\n\nРЕВИЗИЯ 51 (fix_package_1591.py)\nЭкран оплаты распознаётся только по его заголовку «пора оплатить». Стартовая страница оформления\n'
                   '(«выберите способ регистрации») перечисляет шаги «подтвердите данные → оплатите картой → дождитесь\n'
                   'регистрации договора», и по этим словам вкладка на стартовой странице уходила в пуш #оплата с заказом без\n'
                   'регистрации. Страница, предлагающая способ регистрации, оплатой не считается. Маркер: PAYMENT_STRICT_1591R51.\n')


# Revision 52: a message without text no longer stops the controller. r50's /clear check did
# text.split()[0] on the message text; a document, a sticker or a photo has an empty text, the
# IndexError made the update fail, the controller retried the same update every 3 s for ever and
# the bot went silent. The check now tolerates an empty text.
CONTROLLER_OUTPUT_SHA_R50_R51 = "738c0f281ac6e59b6b0a62f07fc27217a73e817b45ceb9b93e1e681c00e21a4b"  # controller of r50..r51 (/clear)
CLEAR_SAFE_MARKER = "CLEAR_SAFE_1591R52"
OLD_CLEAR_SAFE_MARK_R52 = '# CLEAR_BASE_1591R50: /clear in the controller archives and removes processed_numbers.txt and\n'
NEW_CLEAR_SAFE_MARK_R52 = ('# CLEAR_SAFE_1591R52: the controller\'s /clear check tolerates a message without text (a document, a\n'
                           '# sticker); r50\'s text.split()[0] on an empty text made the controller retry one update for ever.\n'
                           '# CLEAR_BASE_1591R50: /clear in the controller archives and removes processed_numbers.txt and\n')
OLD_C_CLEAR_SAFE_R52 = '                    if text.split()[0].lower().split("@")[0] == "/clear":  # CLEAR_BASE_1591R50\n'
NEW_C_CLEAR_SAFE_R52 = '                    if (text.split() or [""])[0].lower().split("@")[0] == "/clear":  # CLEAR_BASE_1591R50 / CLEAR_SAFE_1591R52: a document has no text\n'
README_NOTE_R52 = ('\n\nРЕВИЗИЯ 52 (fix_package_1591.py)\nСообщение без текста больше не останавливает контроллер. Проверка команды /clear из r50 делала\n'
                   'text.split()[0]; у документа, стикера или фото текст пустой, ошибка IndexError роняла обработку, контроллер\n'
                   'повторял одно и то же сообщение каждые 3 с без конца, и бот молчал. Маркер: CLEAR_SAFE_1591R52.\n')

# Revision 53: the basket phone placeholder changed to +7. Use the stable input ID and
# keep the exact legacy placeholder, ignoring hidden form copies. Do not select .first
# or a generic telephone input: the existing Playwright assertions must stay strict.
CONTACT_PHONE_MARKER = "CONTACT_PHONE_FIELD_1591R53"
CONTACT_PHONE_SOURCE_R53 = '''
# CONTACT_PHONE_FIELD_1591R53
def _contact_phone_field(page):
    """Locate the visible basket phone input in the current or legacy form."""
    return page.locator(
        'input#phone-input:visible, input[placeholder="+7 999 999 99"]:visible'
    )


'''
README_NOTE_R53 = ('\n\nРЕВИЗИЯ 53 (fix_package_1591.py)\n'
                  'Поле контактного телефона ищется по id phone-input, с поддержкой старого placeholder.\n'
                  'Исправлены первоначальный ввод и восстановление после reload. Скрытые копии формы\n'
                  'не выбираются; при нескольких видимых совпадениях сохраняется строгая проверка Playwright.\n'
                  'Маркер: CONTACT_PHONE_FIELD_1591R53.\n')

# Revision 54: the auto jobs get the live tool set. The job text asks DeepSeek to «найди причину и
# исправь её» on the page; _explicit_code_change_request matched «исправь» and the code tool set
# (read-only + candidate files, no browser_fill) won over the live one. DeepSeek then saw an empty
# region and contact number, could not type, and answered «🔧 DeepSeek подготовил фикс» with a
# candidate patch instead (tab 3, row 605). An [AUTO_*_ASSIST] job is never a code change request.
AUTO_TOOLS_MARKER = "AUTO_TOOLS_1591R54"
OLD_CODE_REQ_R54 = ('def _explicit_code_change_request(text):\n'
                    '    low = str(text or "").lower().strip()\n'
                    '    if not low:\n'
                    '        return False\n')
NEW_CODE_REQ_R54 = ('def _explicit_code_change_request(text):\n'
                    '    low = str(text or "").lower().strip()\n'
                    '    if not low:\n'
                    '        return False\n'
                    '    # AUTO_TOOLS_1591R54: an auto job asks to «исправь» the page, not the code; the code tool set has no\n'
                    '    # browser_fill and DeepSeek answered with a candidate patch instead of typing the empty field.\n'
                    '    if low.startswith(("[auto_success_assist", "[auto_error_assist")):\n'
                    '        return False\n')
README_NOTE_R54 = ('\n\nРЕВИЗИЯ 54 (fix_package_1591.py)\nDeepSeek в автозадании получает инструменты ввода. Текст автозадания просит «найди причину и исправь\n'
                   'её» на странице, а проверка «просьба изменить код» видела слово «исправь» и выдавала набор для правки\n'
                   'кода без browser_fill/browser_click. DeepSeek видел пустую область и контактный номер, но ввести не мог и\n'
                   'присылал «🔧 DeepSeek подготовил фикс» вместо заполнения. Автозадание [AUTO_*_ASSIST] больше не считается\n'
                   'правкой кода. Маркер: AUTO_TOOLS_1591R54.\n')

# Revision 55: three fixes on the successful (contract) page.
# 1) REGION_FIELD_1591R55: the region input of the contract form can have no id, name, placeholder or
#    linked <label>, only the caption «область» in its wrapper (row 605, tab 3: empty, aria-invalid). The
#    runtime never found it, signed anyway, and after «укажите область» could not fill it either; only
#    DeepSeek could, and with DeepSeek off the tab stood for ever. A visible text input whose own caption
#    is «область»/«регион» is now a candidate as well («район» never is).
# 2) STALE_AUTO_1591R55: unanswered [AUTO_*_ASSIST TAB n] jobs survived a restart, /clear or an update:
#    DeepSeek then worked on «TAB n» that already held another client, and while the stale job waited no
#    fresh job for that tab was queued. They are closed when the automation starts.
# 3) AI_STATUS_1591R55: four tab statuses said «DeepSeek наблюдает» with BEELINE_AI=0.
SUCCESS_PAGE_MARKER = "REGION_FIELD_1591R55"
OLD_REGION_CAND_R55 = ('def _region_input_candidates(page):\n'
                       '    # Prefer semantic attributes and only then nearby label text.\n'
                       '    rx = re.compile(r"(область|регион|region)", re.I)\n'
                       '    return [\n'
                       '        page.locator(\n'
                       '            \'input[name*="region" i], input[id*="region" i], \'\n'
                       '            \'input[name*="area" i], input[id*="area" i], \'\n'
                       '            \'input[placeholder*="область" i], input[aria-label*="область" i], \'\n'
                       '            \'input[placeholder*="регион" i], input[aria-label*="регион" i]\'\n'
                       '        ),\n'
                       '        page.get_by_label(rx),\n'
                       '    ]\n')
NEW_REGION_CAND_R55 = ('# REGION_FIELD_1591R55: the region input may have no id/name/placeholder and no linked <label>, only\n'
                       '# the caption «область» in its wrapper. The script marks a visible enabled text input whose own\n'
                       '# caption (first text line of the nearest wrapper holding no other field) is «область»/«регион».\n'
                       '_REGION_MARK_JS_1591R55 = r"""() => {\n'
                       '  const caption = (el) => {\n'
                       '    let node = el.parentElement;\n'
                       '    for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {\n'
                       '      if (node.querySelectorAll("input, textarea, select").length > 1) break;\n'
                       '      const first = String(node.innerText || "").split("\\n").map((s) => s.trim()).filter(Boolean)[0] || "";\n'
                       '      if (first) return first.toLowerCase();\n'
                       '    }\n'
                       '    return "";\n'
                       '  };\n'
                       '  let marked = 0;\n'
                       '  for (const el of document.querySelectorAll("input")) {\n'
                       '    el.removeAttribute("data-region-1591r55");\n'
                       '    const type = String(el.getAttribute("type") || "text").toLowerCase();\n'
                       '    if (!["text", "search"].includes(type) || el.disabled || el.readOnly) continue;\n'
                       '    const r = el.getBoundingClientRect();\n'
                       '    if (!r.width || !r.height) continue;\n'
                       '    const cap = caption(el);\n'
                       '    if (/^(область|регион)([\\s,/(].*)?$/.test(cap) && !/район/.test(cap)) {\n'
                       '      el.setAttribute("data-region-1591r55", "1");\n'
                       '      marked++;\n'
                       '    }\n'
                       '  }\n'
                       '  return marked;\n'
                       '}"""\n'
                       '\n'
                       '\n'
                       'def _mark_region_input_1591r55(page):\n'
                       '    try:\n'
                       '        return int(page.evaluate(_REGION_MARK_JS_1591R55) or 0)\n'
                       '    except Exception:\n'
                       '        return 0\n'
                       '\n'
                       '\n'
                       'def _region_input_candidates(page):\n'
                       '    # Prefer semantic attributes and only then nearby label text.\n'
                       '    rx = re.compile(r"(область|регион|region)", re.I)\n'
                       '    _mark_region_input_1591r55(page)  # REGION_FIELD_1591R55\n'
                       '    return [\n'
                       '        page.locator(\n'
                       '            \'input[name*="region" i], input[id*="region" i], \'\n'
                       '            \'input[name*="area" i], input[id*="area" i], \'\n'
                       '            \'input[placeholder*="область" i], input[aria-label*="область" i], \'\n'
                       '            \'input[placeholder*="регион" i], input[aria-label*="регион" i]\'\n'
                       '        ),\n'
                       '        page.get_by_label(rx),\n'
                       '        page.locator(\'input[data-region-1591r55="1"]\'),  # REGION_FIELD_1591R55: caption only\n'
                       '    ]\n')
OLD_STALE_DEF_R55 = 'def _ai_db_offset():\n'
NEW_STALE_DEF_R55 = ('def _ai_db_close_stale_auto_1591r55():\n'
                     '    """STALE_AUTO_1591R55: close [AUTO_*_ASSIST TAB n] jobs left unanswered by the previous run. At\n'
                     '    start no worker exists yet, so such a job names a tab that now holds another row."""\n'
                     '    conn = _ai_db_connect()\n'
                     '    try:\n'
                     '        cur = conn.execute(\n'
                     '            "UPDATE inbox SET done_at=?, last_error=?, claimed_by=NULL, claim_until=NULL "\n'
                     '            "WHERE done_at IS NULL AND (body LIKE \'[AUTO_SUCCESS_ASSIST TAB %\' OR body LIKE \'[AUTO_ERROR_ASSIST TAB %\')",\n'
                     '            (time.time(), "STALE_AFTER_RESTART_1591R55"),\n'
                     '        )\n'
                     '        conn.commit()\n'
                     '        return int(cur.rowcount or 0)\n'
                     '    finally:\n'
                     '        conn.close()\n'
                     '\n'
                     '\n'
                     'def _ai_db_offset():\n')
OLD_STALE_CALL_R55 = ('        _ai_db_init()\n'
                      '        print(f"[AI] Durable queue ready: {AI_TELEGRAM_DB.name}", flush=True)\n')
NEW_STALE_CALL_R55 = ('        _ai_db_init()\n'
                      '        stale_auto = _ai_db_close_stale_auto_1591r55()  # STALE_AUTO_1591R55\n'
                      '        if stale_auto:\n'
                      '            print(f"[AI] Закрыто старых автозаданий DeepSeek от прошлого запуска: {stale_auto}", flush=True)\n'
                      '        print(f"[AI] Durable queue ready: {AI_TELEGRAM_DB.name}", flush=True)\n')
AI_STATUS_R55 = (
    ('                "Подтверждение успешно. Кнопка договора пока неактивна — DeepSeek наблюдает/исправляет."\n',
     '                "Подтверждение успешно. Кнопка договора пока неактивна — "\n'
     '                + ("DeepSeek наблюдает/исправляет." if AI_ENABLED_1591R48 else "жду (DeepSeek выключен).")  # AI_STATUS_1591R55\n'),
    ('                "Подтверждение успешно. Ошибка при подписи — DeepSeek помогает, страницу не трогаю."\n',
     '                "Подтверждение успешно. Ошибка при подписи — "\n'
     '                + ("DeepSeek помогает, страницу не трогаю." if AI_ENABLED_1591R48 else "страницу не трогаю (DeepSeek выключен).")  # AI_STATUS_1591R55\n'),
    ('            "Подтверждение успешно. Жду/проверяю интерфейс договора; DeepSeek наблюдает."\n',
     '            "Подтверждение успешно. Жду/проверяю интерфейс договора"\n'
     '            + ("; DeepSeek наблюдает." if AI_ENABLED_1591R48 else " (DeepSeek выключен).")  # AI_STATUS_1591R55\n'),
    ('        "Подтверждение успешно. Подпись ещё не завершилась — DeepSeek наблюдает и помогает."\n',
     '        "Подтверждение успешно. Подпись ещё не завершилась — "\n'
     '        + ("DeepSeek наблюдает и помогает." if AI_ENABLED_1591R48 else "жду (DeepSeek выключен).")  # AI_STATUS_1591R55\n'),
)
# 4) GUARD_BROWSER_1591R55: when a Chromium stopped answering CDP for BROWSER_HANG_RESTART_SECONDS the
#    watchdog restarted the whole browser and killed every tab in it, the tab on the contract page too
#    (tab 6, row on personal-data-form while DeepSeek was filling the region: the slot took the next
#    row). While a tab of that Chromium is under success/error guard the browser is not restarted; a
#    Chromium whose process has exited is still replaced (its pages are gone anyway).
GUARD_BROWSER_HELPER_R55 = ('# GUARD_BROWSER_1591R55: a tab on the contract page (success/error guard) is never killed by a restart.\n'
                            'GUARDED_PHASES_1591R55 = {"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP", "ERROR_ASSIST"}\n'
                            '\n'
                            '\n'
                            'def _tab_guarded_1591r55(info):\n'
                            '    info = info or {}\n'
                            '    return (bool(info.get("success_guard")) or bool(info.get("error_guard"))\n'
                            '            or str(info.get("phase") or "") in GUARDED_PHASES_1591R55)\n'
                            '\n'
                            '\n'
                            'def _drain_deadline_1591r32(base_dir, processes, heartbeat):\n')
OLD_GUARD_HELPER_R55 = 'def _drain_deadline_1591r32(base_dir, processes, heartbeat):\n'
OLD_GUARD_DEF_R55 = '        def restart_browser_instance(browser_idx, reason):  # BROWSER_HANG_1591R18\n'
NEW_GUARD_DEF_R55 = ('        browser_restart_held_at = {}  # GUARD_BROWSER_1591R55: last «not restarting» notice per Chromium\n'
                     '\n'
                     '        def restart_browser_instance(browser_idx, reason):  # BROWSER_HANG_1591R18\n')
OLD_GUARD_HEAD_R55 = ('            instance = browser_instances[browser_idx]\n'
                      '            first_tab = browser_idx * TABS_PER_BROWSER + 1\n'
                      '            tab_ids = [t for t in range(first_tab, first_tab + TABS_PER_BROWSER) if t in processes]\n')
NEW_GUARD_HEAD_R55 = (OLD_GUARD_HEAD_R55 +
                      '            # GUARD_BROWSER_1591R55: never kill a tab on the contract page. While one is there the hung\n'
                      '            # Chromium is left alone (False); only a Chromium whose process has exited is replaced.\n'
                      '            guarded_tabs = [t for t in tab_ids if _tab_guarded_1591r55(heartbeat.get(str(t)))]\n'
                      '            chromium_proc = instance.get("proc")\n'
                      '            chromium_alive = chromium_proc is None or chromium_proc.poll() is None\n'
                      '            if guarded_tabs and chromium_alive:\n'
                      '                if monotonic() - float(browser_restart_held_at.get(browser_idx) or 0) >= 60:\n'
                      '                    browser_restart_held_at[browser_idx] = monotonic()\n'
                      '                    print(\n'
                      '                        f"[BROWSER RESTART] Chromium #{instance[\'id\']}: {reason} Не перезапускаю: "\n'
                      '                        f"вкладки {guarded_tabs} на странице договора (SUCCESS GUARD).",\n'
                      '                        flush=True,\n'
                      '                    )\n'
                      '                return False\n')
OLD_GUARD_TAIL_R55 = ('            for tab_id, row in plans:\n'
                      '                new_proc, _ = spawn_worker(tab_id, row)\n'
                      '                processes[tab_id] = new_proc\n')
NEW_GUARD_TAIL_R55 = OLD_GUARD_TAIL_R55 + '            return True  # GUARD_BROWSER_1591R55\n'
OLD_GUARD_CALL_R55 = ('                    if hang >= BROWSER_HANG_RESTART_SECONDS:\n'
                      '                        restart_browser_instance(\n'
                      '                            browser_idx,\n'
                      '                            f"CDP не отвечает {int(hang)} сек (вкладка {tab_id}: {reason})",\n'
                      '                        )\n'
                      '                        return True\n')
NEW_GUARD_CALL_R55 = ('                    if hang >= BROWSER_HANG_RESTART_SECONDS and restart_browser_instance(  # GUARD_BROWSER_1591R55\n'
                      '                        browser_idx,\n'
                      '                        f"CDP не отвечает {int(hang)} сек (вкладка {tab_id}: {reason})",\n'
                      '                    ):\n'
                      '                        return True\n')
GUARD_BROWSER_R55 = ((OLD_GUARD_HELPER_R55, GUARD_BROWSER_HELPER_R55), (OLD_GUARD_DEF_R55, NEW_GUARD_DEF_R55),
                     (OLD_GUARD_HEAD_R55, NEW_GUARD_HEAD_R55), (OLD_GUARD_TAIL_R55, NEW_GUARD_TAIL_R55),
                     (OLD_GUARD_CALL_R55, NEW_GUARD_CALL_R55))
README_NOTE_R55 = ('\n\nРЕВИЗИЯ 55 (fix_package_1591.py)\nТри исправления на успешной странице.\n'
                   '1) Поле «область» без id, name, placeholder и связанной подписи (только надпись «область» рядом) теперь\n'
                   'находится: бот впишет «Саратовская область» сам, если поле пустое. Раньше его находил только DeepSeek, а при\n'
                   'выключенном DeepSeek вкладка стояла бесконечно. Поле «район» не трогается.\n'
                   '2) Незавершённые автозадания DeepSeek прошлого запуска закрываются при старте: после рестарта, /clear или\n'
                   'обновления DeepSeek больше не работает по старому заданию с вкладкой, где уже другой клиент, и новые задания\n'
                   'для этой вкладки не блокируются.\n'
                   '3) При BEELINE_AI=0 статусы вкладки больше не пишут «DeepSeek наблюдает».\n'
                   '4) Браузер с вкладкой на странице договора больше не перезапускается, когда другая его вкладка зависла:\n'
                   'раньше перезапуск убивал и вкладку на подписании, а слот брал следующую строку. Chromium, процесс\n'
                   'которого уже завершился, по-прежнему перезапускается.\n'
                   'Маркеры: REGION_FIELD_1591R55, STALE_AUTO_1591R55, AI_STATUS_1591R55, GUARD_BROWSER_1591R55.\n')

# Revision 56: DeepSeek no longer writes reports. The auto jobs and the system prompt demanded a
# detailed mini-report after every intervention (7 points, an example, the URL), sent to Telegram;
# it cost output tokens on every job and input tokens on every request (the rules travel in the
# system prompt). The runtime never parsed the VERDICT line (the prompt said it did). The answer to
# an auto job is now ONE short line: what was set (field = value) and the VERDICT.
SHORT_REPORT_MARKER = "SHORT_REPORT_1591R56"
SHORT_REPORT_LINES_R56 = (
    ('        "В конце ОБЯЗАТЕЛЬНО отправь пользователю короткий мини-отчёт: что было не так; "\n'
     '        "что ты изменил; какие значения поставил; стала ли кнопка активна; нажал ли её; "\n'
     '        "чем закончилось подписание; на каком URL/экране осталась вкладка. "\n'
     '        "Пример формата: «Не был указан город, поэтому подтверждение договора не проходило. "\n'
     '        "Поставил город — Саратов. Кнопка стала активна, нажал “Подписать договор”. "\n'
     '        "Подписание прошло успешно. Вкладка осталась на …». "\n',
     '        "ОТЧЁТ НЕ ПИШИ (SHORT_REPORT_1591R56): весь ответ — ОДНА короткая строка: что поставил "\n'
     '        "(поле = значение) или «ничего не менял», затем VERDICT. "\n'),
    ('        "ПОСЛЕДНЯЯ СТРОКА ОТЧЁТА СТРОГО одна из: «VERDICT: SIGNED» (checksignature 200 или экран после "\n',
     '        "VERDICT строго одно из: «VERDICT: SIGNED» (checksignature 200 или экран после "\n'),
    ('        "странице. Затем ОБЯЗАТЕЛЬНО отправь мини-отчёт: причина, что проверил, что "\n'
     '        "попробовал, результат, URL. Сразу после твоего отчёта runtime автоматически, без "\n',
     '        "странице. Отчёт не пиши (SHORT_REPORT_1591R56): ответь ОДНОЙ короткой строкой — причина. "\n'
     '        "Сразу после твоего ответа runtime автоматически, без "\n'),
    ('- Последняя строка каждого отчёта SUCCESS SUPERVISOR СТРОГО одна из: «VERDICT: SIGNED»,\n'
     '  «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина».\n'
     '  Runtime читает эту строку: SIGNED фиксирует успех, PAYMENT — шаг оплаты, NOT_SIGNED —\n'
     '  вкладка удерживается и уходит на проверку пользователю.\n',
     '- Ответ на автозадание SUCCESS SUPERVISOR — ОДНА короткая строка: что изменил (поле = значение)\n'
     '  и VERDICT: «VERDICT: SIGNED», «VERDICT: PAYMENT» (экран «пора оплатить eSIM») или\n'
     '  «VERDICT: NOT_SIGNED — причина». Подробных отчётов не пиши (SHORT_REPORT_1591R56).\n'),
    ('- После каждого автономного вмешательства ОБЯЗАТЕЛЬНО дай пользователю мини-отчёт:\n'
     '  (1) что мешало; (2) что изменил; (3) конкретные поставленные значения;\n'
     '  (4) состояние кнопки; (5) нажал ли «Подписать договор»; (6) результат;\n'
     '  (7) текущий URL/экран. Не пиши абстрактно «исправил» — перечисляй фактические действия.\n',
     '- Мини-отчётов после вмешательства не пиши: только одна строка итога (см. выше).\n'),
)
SHORT_REPORT_LINES_R56 += (
    ('        "варианты — тогда перечисли их в отчёте. "\n',
     '        "варианты — тогда перечисли их в ответе одной строкой. "\n'),
    ('        "registration/error открыта; проанализируй DOM/console/network и отправь отчёт",\n',
     '        "registration/error открыта; проанализируй DOM/console/network",\n'),
)
# Sentences inside the one-line mission constants: the whole line is rewritten at build time.
SHORT_REPORT_SENTENCES_R56 = (
    ("После автономного вмешательства отправляй краткий фактический отчёт: блокер, проверки, "
     "изменения/значения, состояние действия, результат и текущий URL.",
     "После автономного вмешательства отчёт не пиши: одна короткая строка с изменёнными значениями."),
    ("После вмешательства отправляй фактический мини-отчёт: блокер, что проверил, что именно изменил "
     "и на какие значения, состояние кнопки подписания, действие/результат и финальный URL.",
     "После вмешательства отчёт не пиши: одна короткая строка — что изменил и VERDICT."),
)
README_NOTE_R56 = ('\n\nРЕВИЗИЯ 56 (fix_package_1591.py)\nDeepSeek больше не пишет отчёты. Автозадания и системная подсказка требовали подробный мини-отчёт\n'
                   'после каждого вмешательства (7 пунктов, пример, URL); это тратило токены на каждом задании, а правила\n'
                   'уходили с каждым запросом. Строку VERDICT бот никогда не читал. Теперь ответ на автозадание — одна\n'
                   'короткая строка: что поставил (поле = значение) и VERDICT. Маркер: SHORT_REPORT_1591R56.\n')

# Revision 57: DeepSeek stays quiet in the normal flow. On every ordinary success the contract page
# loads with the button disabled or not yet rendered, and the button stays a few seconds after a
# good click; each of these queued a DeepSeek job at once, DeepSeek found nothing to do and still
# answered in Telegram (two messages). Now (1) these three triggers wait QUIET_WAIT_SECONDS on the
# same row and URL first; (2) a job whose tab already left the page it was queued for is closed
# without calling DeepSeek; (3) the answer is one line «Вкладка N: …», and «-» (nothing was needed)
# is not sent at all.
QUIET_AUTO_MARKER = "QUIET_AUTO_1591R57"
QUIET_HELPERS_R57 = r'''# QUIET_AUTO_1591R57: no DeepSeek job, and no Telegram line, when its help is not needed.
QUIET_REPLY_1591R57 = "\x00quiet"
QUIET_WAIT_SECONDS_1591R57 = 45
_AUTO_JOB_RE_1591R57 = re.compile(r"^\[AUTO_(?:SUCCESS|ERROR)_ASSIST TAB (\d+)\]")
_AUTO_URL_RE_1591R57 = re.compile(r"URL: (\S+)\s*$")


def _is_auto_job_1591r57(body):
    return bool(_AUTO_JOB_RE_1591R57.match(str(body or "").strip()))


def _auto_job_outdated_1591r57(body, pages):
    """True when the job's tab is listed and none of its pages is still on the URL the job was queued for."""
    text = str(body or "").strip()
    m = _AUTO_JOB_RE_1591R57.match(text)
    u = _AUTO_URL_RE_1591R57.search(text)
    if not m or not u:
        return False
    def norm(url):
        return str(url or "").split("#")[0].split("?")[0].rstrip("/")
    want = norm(u.group(1))
    urls = [norm(p.get("url")) for p in (pages or []) if p.get("tab_id") == int(m.group(1))]
    return bool(want) and bool(urls) and want not in urls


def _auto_error_reply_1591r57(body, text):
    """QUIET_ERRORS_1591R57: an auto job's own error is printed to the journal and not sent to Telegram."""
    if _is_auto_job_1591r57(body):
        print("[AI AUTO] " + str(text)[:500], flush=True)
        return QUIET_REPLY_1591R57
    return text


def _ai_db_complete_silent_1591r57(update_id):
    conn = _ai_db_connect()
    try:
        conn.execute(
            "UPDATE inbox SET done_at=?, last_error=NULL, claimed_by=NULL, claim_until=NULL WHERE update_id=?",
            (time.time(), int(update_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _ai_db_complete(update_id, chat_id, response_text):
'''
QUIET_WAIT_HELPER_R57 = '''def _quiet_wait_1591r57(worker, key):
    """QUIET_AUTO_1591R57: True once the same condition has lasted QUIET_WAIT_SECONDS_1591R57 on this row and URL
    (a contract page that is still loading, or a button that stays a few seconds after a good click)."""
    try:
        url = str(worker.get("page").url or "")
    except Exception:
        url = ""
    mark = [str(worker.get("row")), url]
    state = worker.get(key)
    now = monotonic()
    if not state or state.get("mark") != mark:
        state = {"mark": mark, "since": now}
        worker[key] = state
    return now - float(state["since"]) >= QUIET_WAIT_SECONDS_1591R57


def queue_success_assist(worker, reason, force=False):
'''
QUIET_PAIRS_R57 = (
    ('def _ai_db_complete(update_id, chat_id, response_text):\n', QUIET_HELPERS_R57),
    ('    """Finish the AI job and durably queue its Telegram response."""\n',
     '    """Finish the AI job and durably queue its Telegram response."""\n'
     '    if response_text == globals().get("QUIET_REPLY_1591R57"):  # QUIET_AUTO_1591R57: an auto job with nothing to tell\n'
     '        _ai_db_complete_silent_1591r57(update_id)\n'
     '        return\n'
     '    import re as _re_1591r57  # QUIET_AUTO_1591R57: the VERDICT tag is for the bot, not for the chat\n'
     '    response_text = _re_1591r57.sub(r"\\s*VERDICT:\\s*(?:SIGNED|PAYMENT|NOT_SIGNED)\\b[^\\n]*", "", str(response_text)).strip() or str(response_text)\n'),
    ('def queue_success_assist(worker, reason, force=False):\n', QUIET_WAIT_HELPER_R57),
    ('            queue_success_assist(worker, "кнопка «Подписать договор» неактивна")\n',
     '            if _quiet_wait_1591r57(worker, "quiet_button_1591r57"):  # QUIET_AUTO_1591R57: the site may still be filling the form\n'
     '                queue_success_assist(worker, "кнопка «Подписать договор» неактивна")\n'),
    ('        queue_success_assist(worker, "интерфейс договора требует наблюдения")\n',
     '        if _quiet_wait_1591r57(worker, "quiet_contract_ui_1591r57"):  # QUIET_AUTO_1591R57: the page may still be loading\n'
     '            queue_success_assist(worker, "интерфейс договора требует наблюдения")\n'),
    ('    queue_success_assist(worker, "подпись остаётся на странице; проверь ошибки/обязательные поля")\n',
     '    if _quiet_wait_1591r57(worker, "quiet_sign_wait_1591r57"):  # QUIET_AUTO_1591R57: the site may still be answering\n'
     '        queue_success_assist(worker, "подпись остаётся на странице; проверь ошибки/обязательные поля")\n'),
    ('            pages = _observer_collect_pages(cdp_urls, with_screenshots=False) if cdp_urls else []\n',
     '            pages = _observer_collect_pages(cdp_urls, with_screenshots=False) if cdp_urls else []\n'
     '            if _auto_job_outdated_1591r57(latest, pages):  # QUIET_AUTO_1591R57: the tab already left that page\n'
     '                (globals().get("_ai_success_verdict_1591r30") or (lambda *a: None))(status_map, latest, "")  # full build: busy flag off\n'
     '                _ai_db_complete_silent_1591r57(update_id)\n'
     '                print(f"[AI {lane.upper()}] update {update_id}: вкладка уже ушла с этой страницы — DeepSeek не вызываю.", flush=True)\n'
     '                _ai_health_touch(ai_health, "idle")\n'
     '                continue\n'),
    ('                            + str(plan.get("summary") or "Готово.")\n',
     '                            + str(plan.get("summary") or "Готово.")\n'
     '                        ) if not _is_auto_job_1591r57(latest) else (  # QUIET_AUTO_1591R57: one line, «-» stays silent\n'
     '                            QUIET_REPLY_1591R57 if str(plan.get("summary") or "").strip() in {"", "-", "—", "–"}\n'
     '                            else "🤖 " + str(plan.get("summary") or "").strip()\n'),
    ('        "ОТЧЁТ НЕ ПИШИ (SHORT_REPORT_1591R56): весь ответ — ОДНА короткая строка: что поставил "\n',
     '        "ОТЧЁТ НЕ ПИШИ (SHORT_REPORT_1591R56, QUIET_AUTO_1591R57). Если ты что-то изменил или нажал — ответ "\n'
     '        f"2–3 коротких предложения по факту, например: «Вкладка {tab_id}: не было области. Заполнил "\n'
     '        "«Саратовская область». Подпись прошла.» Без технических подробностей: никаких селекторов, DOM, "\n'
     '        "кода, URL, network и рассуждений. Если вмешиваться не понадобилось (сайт сам продвинулся, уже "\n'
     '        "подписано, ничего не менял) — ответь ровно «-». "\n'),
    ('        "VERDICT строго одно из: «VERDICT: SIGNED» (checksignature 200 или экран после "\n',
     '        "Последнее предложение — итог: «Подпись прошла», «Дошло до оплаты» или «Не подписано — причина». "\n'),
    ('        "подписи), «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина». "\n',
     '        "Последней отдельной строкой — служебная метка для бота, в чат она не уходит: «VERDICT: SIGNED», "\n'
     '        "«VERDICT: PAYMENT» или «VERDICT: NOT_SIGNED». "\n'),
    ('        "(поле = значение) или «ничего не менял», затем VERDICT. "\n', ''),
    ('- Ответ на автозадание SUCCESS SUPERVISOR — ОДНА короткая строка: что изменил (поле = значение)\n',
     '- Ответ на автозадание SUCCESS SUPERVISOR — 2–3 коротких предложения по факту: чего не хватало,\n'),
    ('  и VERDICT: «VERDICT: SIGNED», «VERDICT: PAYMENT» (экран «пора оплатить eSIM») или\n',
     '  что заполнил (значение) и итог: «Подпись прошла», «Дошло до оплаты» или «Не подписано — причина».\n'),
    ('  «VERDICT: NOT_SIGNED — причина». Подробных отчётов не пиши (SHORT_REPORT_1591R56).\n',
     '  Последней строкой — служебная метка для бота: «VERDICT: SIGNED», «VERDICT: PAYMENT» или «VERDICT: NOT_SIGNED».\n'
     '  Подробных отчётов не пиши (SHORT_REPORT_1591R56): без селекторов, DOM, кода и URL. Если вмешиваться\n'
     '  не понадобилось — ответь ровно «-» (QUIET_AUTO_1591R57).\n'),
    # QUIET_ERRORS_1591R57: a skipped error row and an auto job's own error go to the journal, not to Telegram.
    ('            _io1591.enqueue_notice(\n'
     '                globals(), chat,\n'
     '                f"⏭ Вкладка {worker[\'id\']}: строка {key} пропущена без повтора: {reason}. "\n'
     '                "Worker продолжает со следующей строкой.",\n'
     '            )\n',
     '            print(  # QUIET_ERRORS_1591R57: journal only, no Telegram push\n'
     '                f"⏭ Вкладка {worker[\'id\']}: строка {key} пропущена без повтора: {reason}. "\n'
     '                "Worker продолжает со следующей строкой.",\n'
     '                flush=True,\n'
     '            )\n'),
    ('            _io1591.enqueue_notice(\n'
     '                globals(), chat,\n'
     '                f"⏭ Вкладка {worker[\'id\']}: строка {key} пропущена после повторной "\n'
     '                f"registration/error ({reason}). Worker продолжает со следующей строкой.",\n'
     '            )\n',
     '            print(  # QUIET_ERRORS_1591R57: journal only, no Telegram push\n'
     '                f"⏭ Вкладка {worker[\'id\']}: строка {key} пропущена после повторной "\n'
     '                f"registration/error ({reason}). Worker продолжает со следующей строкой.",\n'
     '                flush=True,\n'
     '            )\n'),
    ('                    response_text = "⚠️ Developer: " + dev_err\n',
     '                    response_text = _auto_error_reply_1591r57(latest, "⚠️ Developer: " + dev_err)  # QUIET_ERRORS_1591R57\n'),
    ('                "SELECT chat_id FROM inbox WHERE update_id=?",\n',
     '                "SELECT chat_id, body FROM inbox WHERE update_id=?",  # QUIET_ERRORS_1591R57\n'),
    ('            chat_id = str(row[0]) if row else ""\n',
     '            quiet_auto = globals().get("_is_auto_job_1591r57") or (lambda body: False)  # QUIET_ERRORS_1591R57\n'
     '            chat_id = str(row[0]) if row and not quiet_auto(row[1]) else ""  # auto job errors stay in the journal\n'),
)
# a line of its own before the r48 switch: the lite → full step still finds «'AI_ENABLED_1591R48':True,'_ai_db_fail'»
OLD_TEST_QUIET_NS_R57 = "            'AI_ENABLED_1591R48':True,"
NEW_TEST_QUIET_NS_R57 = ("            '_auto_job_outdated_1591r57':lambda *a:False,'_is_auto_job_1591r57':lambda *a:False,"
                         "'QUIET_REPLY_1591R57':'quiet','_auto_error_reply_1591r57':lambda b,t:t,\n"
                         "            'AI_ENABLED_1591R48':True,")
QUIET_SENTENCES_R57 = (
    ("После автономного вмешательства отчёт не пиши: одна короткая строка с изменёнными значениями.",
     "После автономного вмешательства отчёт не пиши: 2–3 коротких предложения по факту, без технических подробностей."),
    ("После вмешательства отчёт не пиши: одна короткая строка — что изменил и VERDICT.",
     "После вмешательства отчёт не пиши: 2–3 коротких предложения — чего не хватало, что заполнил и итог."),
)
README_NOTE_R57 = ('\n\nРЕВИЗИЯ 57 (fix_package_1591.py)\nDeepSeek молчит в обычном потоке. При каждом обычном успехе страница договора открывается с\n'
                   'неактивной или ещё не появившейся кнопкой, а после удачного клика кнопка держится несколько секунд; в\n'
                   'каждом из этих случаев бот сразу ставил задание, DeepSeek ничего не делал и всё равно писал в Telegram.\n'
                   'Теперь эти три повода ждут 45 с на той же строке и странице; задание, чья вкладка уже ушла с той\n'
                   'страницы, закрывается без вызова DeepSeek; ответ — одна строка «Вкладка N: …», а «-» (помощь не\n'
                   'понадобилась) в Telegram не отправляется. Ответ DeepSeek — 2–3 предложения по факту, без технических\n'
                   'подробностей. Пуши «строка пропущена после registration/error» и ошибки DeepSeek по автозаданиям\n'
                   'уходят только в журнал. В «Мои eSIM» кнопки 🗑 (одну, отмеченные ✅/❌, все с подтверждением) убирают\n'
                   'eSIM из списка, файлы результатов остаются; в меню строка «Новых eSIM за сегодня».\n'
                   'Маркеры: QUIET_AUTO_1591R57, QUIET_ERRORS_1591R57, MENU_DELETE_1591R57.\n')

# Revision 58: the menu checks the order links and deletes only after a confirmation. «🔗 Проверить
# ссылки» in «Мои eSIM» opens every order link in its own headless Chromium (read-only) and marks it
# ❌ / 💳 / ✅ / ❔; «🗑 Удалить ✅ и ❌» asks first (42 eSIMs of a colleague's bot vanished on one
# tap), «↩️ Вернуть удалённые» brings them back, and every deleting press goes to the journal with
# the Telegram name of who pressed it. The runtime only carries the marker; the menu module ships.
LINK_CHECK_MARKER = "LINK_CHECK_1591R58"
OLD_LINK_MARK_R58 = 'SUCCESS_PROFILE_FIELDS = [\n'
NEW_LINK_MARK_R58 = ('# LINK_CHECK_1591R58: «🔗 Проверить ссылки», the confirmation of «🗑 Удалить ✅ и ❌» and «↩️ Вернуть\n'
                     '# удалённые» live in telegram_menu.py; the menu reads these fields for the eSIM card.\n'
                     'SUCCESS_PROFILE_FIELDS = [\n')
README_NOTE_R58 = ('\n\nРЕВИЗИЯ 58 (fix_package_1591.py)\nПроверка ссылок и безопасное удаление в меню. В «Мои eSIM» кнопка «🔗 Проверить ссылки»\n'
                   'открывает каждую ссылку заказа в отдельном невидимом Chromium (ничего не нажимает) и отмечает её: ❌ не\n'
                   'работает, 💳 ждёт оплаты, ✅ оплачена/готова, ❔ непонятно (со словами самой страницы). «🗑 Удалить ✅ и ❌»\n'
                   'теперь спрашивает подтверждение, «↩️ Вернуть удалённые» возвращает скрытые eSIM, а каждое удаление\n'
                   'пишется в журнал с именем того, кто нажал. Маркеры: LINK_CHECK_1591R58, MENU_SAFE_DELETE_1591R58.\n')

# Revision 59: the link check read the site's errorCode "NONE" (no error) as an error and marked a
# valid order at the payment step ❌ (selfregStatus DOCS_GENERATED, «теперь пора оплатить eSIM»).
# "NONE" is no error now, DOCS_GENERATED is «ждёт оплаты», and the r58 results stored with that
# mistake are corrected when the menu starts. The runtime only carries the marker; the menu ships.
LINK_STATUS_MARKER = "LINK_STATUS_1591R59"
OLD_LINK_STATUS_MARK_R59 = 'SUCCESS_PROFILE_FIELDS = [\n'
NEW_LINK_STATUS_MARK_R59 = ('# LINK_STATUS_1591R59: the link check takes errorCode NONE for «no error» and DOCS_GENERATED for\n'
                            '# «ждёт оплаты» (telegram_menu.py).\n'
                            'SUCCESS_PROFILE_FIELDS = [\n')
README_NOTE_R59 = ('\n\nРЕВИЗИЯ 59 (fix_package_1591.py)\nПроверка ссылок не путает «ошибки нет» с ошибкой. Сайт отвечает errorCode NONE, когда ошибки нет, а\n'
                   'проверка r58 считала это ошибкой и ставила ❌ рабочему заказу на шаге оплаты (selfregStatus DOCS_GENERATED,\n'
                   '«теперь пора оплатить eSIM»). Теперь NONE — не ошибка, DOCS_GENERATED — «ждёт оплаты», ESIM_SUCCESS\n'
                   '(«срок установки eSIM истёк») — «📲 уже использована»; статус сайта главнее слов страницы, а сохранённые\n'
                   'результаты r58 с этой ошибкой исправляются при запуске меню. Маркер: LINK_STATUS_1591R59.\n')

# Revision 60: the bot's own tools in the menu. One status per eSIM (🆕 💳 ☑️ ⛔ ❌, a manual ☑️/❌ wins over
# the link check) plus a manual 🏦 flag; «Показать: Все ⇄ Только: 💳» in «Мои eSIM», deleting in the card only;
# 📤 export of the 💳 ones (🟢 one message per eSIM with 🔼/🔽 and ☑️ 🏦 ↩️, ‼️ number + link lists, or a .txt)
# with «🔄 Обновить статус ссылок» and a report; 🔁 «Обновить статусы» (💳 / все) and /recheck 24h|1d|off;
# ⚙️ settings (tariff, browsers, tabs, DeepSeek, scheduled restart) written as a systemd drop-in; 🖥 server;
# ⬆️ self-update through systemd-run with the result after the restart; a notice after a reboot or a crash.
# The controller gets two hooks: menu.on_start() and menu.handle_text() before its commands.
BOT_TOOLS_MARKER = "BOT_TOOLS_1591R60"
OLD_BOT_TOOLS_MARK_R60 = 'SUCCESS_PROFILE_FIELDS = [\n'
NEW_BOT_TOOLS_MARK_R60 = ('# BOT_TOOLS_1591R60: export, statuses, /recheck, settings, server and self-update live in\n'
                          '# telegram_menu.py; the controller calls menu.on_start() and menu.handle_text().\n'
                          'SUCCESS_PROFILE_FIELDS = [\n')
OLD_C_MENU_START_R60 = '    menu = _menu_mod.TelegramMenu(app, BASE_DIR, proc, link_resolver=_row_link_command)\n'
NEW_C_MENU_START_R60 = ('    menu = _menu_mod.TelegramMenu(app, BASE_DIR, proc, link_resolver=_row_link_command)\n'
                        '    try:\n'
                        '        menu.on_start()  # BOT_TOOLS_1591R60: notices after a reboot, a crash, an update or a setting\n'
                        '    except Exception as exc:\n'
                        '        print(f"[CTRL] меню on_start: {exc}", flush=True)\n')
OLD_C_MENU_TEXT_R60 = '                    if text in {"/start", "/menu"}:\n'
NEW_C_MENU_TEXT_R60 = ('                    if text and menu.handle_text(text):  # BOT_TOOLS_1591R60: the export count, /recheck\n'
                       '                        waiting_upload = False\n'
                       '                        continue\n'
                       '\n'
                       '                    if text in {"/start", "/menu"}:\n')
OLD_TEST_MENU_NS_R60 = 'retire_status_messages=lambda *a:0))'
NEW_TEST_MENU_NS_R60 = 'retire_status_messages=lambda *a:0,handle_text=lambda t:False,on_start=lambda:None))'
README_NOTE_R60 = ('\n\nРЕВИЗИЯ 60 (fix_package_1591.py)\nИнструменты бота в меню. У каждой eSIM один статус (🆕 новая, 💳 ждёт оплаты, ☑️ готово, ⛔ ссылка не\n'
                   'работает, ❌ брак; ручная отметка главнее проверки) и ручной значок 🏦 после него. «Мои eSIM»: переключатель\n'
                   '«Показать: Все / Только: 💳», удаление только в карточке. 📤 Выгрузка eSIM 💳: 🟢 обычная (сообщение на каждую\n'
                   'eSIM с 🔼/🔽 и ☑️ 🏦 ↩️) или ‼️ срочная (номер и ссылка списком), сообщением или файлом .txt, количество числом\n'
                   'или «Все», затем «🔄 Обновить статус ссылок» с отчётом. 🔁 Обновить статусы (💳 или все) и /recheck 24h, 1d,\n'
                   'off. ⚙️ Настройки: тариф, браузеры, вкладки, DeepSeek, плановый перезапуск. 🖥 Сервер. ⬆️ Обновить бота по\n'
                   'кнопке с результатом после перезапуска. Сообщение после перезагрузки сервера или сбоя бота.\n'
                   'Маркер: BOT_TOOLS_1591R60.\n')

# Revision 61: the menu only. «Мои eSIM» keeps the r59 look (🕒 date and time, the counters, the full card)
# with the new status icons; «готово» is the green ✅ again. The 🟢 export message is the push card, and
# «🔄 Обновить» re-sends the still waiting eSIMs the way the export gave them (cards, a list or a .txt).
EXPORT_CARDS_MARKER = "EXPORT_CARDS_1591R61"
OLD_EXPORT_CARDS_MARK_R61 = '# telegram_menu.py; the controller calls menu.on_start() and menu.handle_text().\n'
NEW_EXPORT_CARDS_MARK_R61 = ('# telegram_menu.py; the controller calls menu.on_start() and menu.handle_text().\n'
                             '# EXPORT_CARDS_1591R61: «Мои eSIM» as in r59 with the status icons, export refresh as the export.\n')
README_NOTE_R61 = ('\n\nРЕВИЗИЯ 61 (fix_package_1591.py)\nТолько меню. «Мои eSIM» снова как в r59: 🕒 дата и время у номера, счётчики, полная\n'
                   'карточка; поменялись только значки статуса, «готово» снова зелёная ✅. Сообщение обычной выгрузки — как\n'
                   'пуш. «🔄 Обновить» после обычной выгрузки присылает неоплаченные так же, как выгрузка: карточками с\n'
                   'кнопками (срочная — списком, .txt — файлом), и снова кнопку «🔄 Обновить» уже для них.\n'
                   'Меню переставлено по рисунку: 📱 Мои eSIM сверху, ▶️ ⏹ 🔄 и 📊 Статус ниже, ⬆️ Обновить бота внизу.\n'
                   'Маркер: EXPORT_CARDS_1591R61.\n')

# Revision 62: the menu only. selfregStatus ESIM_SUCCESS («срок установки eSIM истёк») is an eSIM already issued:
# ✅ «eSIM уже выпущена» even when the page lands on /error or answers 4xx; saved ⛔ results of it are corrected.
ESIM_ISSUED_MARKER = "ESIM_ISSUED_1591R62"
OLD_ESIM_ISSUED_MARK_R62 = '# EXPORT_CARDS_1591R61: «Мои eSIM» as in r59 with the status icons, export refresh as the export.\n'
NEW_ESIM_ISSUED_MARK_R62 = ('# EXPORT_CARDS_1591R61: «Мои eSIM» as in r59 with the status icons, export refresh as the export.\n'
                            '# ESIM_ISSUED_1591R62: the link check takes selfregStatus ESIM_SUCCESS for an issued eSIM (✅).\n')
README_NOTE_R62 = ('\n\nРЕВИЗИЯ 62 (fix_package_1591.py)\nТолько меню. Проверка ссылки: selfregStatus=ESIM_SUCCESS («срок установки eSIM истёк») —\n'
                   'это уже выпущенная eSIM: ✅ «eSIM уже выпущена», даже если страница ушла на /error или ответила 4xx. Старые\n'
                   'результаты проверки с ⛔ для таких eSIM исправляются при запуске бота. Маркер: ESIM_ISSUED_1591R62.\n')

# Revision 64: «📂 База» and «🔢 Генерация» (first published by hand as r63, now built here). The upload is
# filtered before it becomes clients.txt: «номер|паспорт|даты рождения…» lines need a 10-digit passport and a
# birth year of 1980 or later (one of several dates is enough); other lines keep the format batch_support.load_clients
# reads (10/11-digit number, then the passport after a tab, |, ;, , or a space) and need a 10-digit passport.
# «➕ Добавить строки» appends to clients.txt without stopping the work; the controller starts the added rows when
# the current queue ends. «🆕 Загрузить новую базу» stops, replaces the base and starts it.
BASE_TOOLS_MARKER = "BASE_TOOLS_1591R64"
OLD_BASE_TOOLS_MARK_R64 = '# ESIM_ISSUED_1591R62: the link check takes selfregStatus ESIM_SUCCESS for an issued eSIM (✅).\n'
NEW_BASE_TOOLS_MARK_R64 = ('# ESIM_ISSUED_1591R62: the link check takes selfregStatus ESIM_SUCCESS for an issued eSIM (✅).\n'
                           '# BASE_TOOLS_1591R64: the controller filters uploaded bases and appends rows; the menu has «📂 База» and «🔢 Генерация».\n')
OLD_C_PENDING_R64 = 'PROCESSED_FILE = BASE_DIR / "processed_numbers.txt"\n'
NEW_C_PENDING_R64 = ('PROCESSED_FILE = BASE_DIR / "processed_numbers.txt"\n'
                     'APPEND_PENDING_FILE = BASE_DIR / ".base_append_pending"  # BASE_TOOLS_1591R64: added rows wait for the queue\n')
OLD_C_FILTER_R64 = 'def _download_document(file_id, destination):\n'
NEW_C_FILTER_R64 = '''# BASE_TOOLS_1591R64: «📂 База». An uploaded file is filtered into «номер паспорт» lines before it is used.
def _phone_digits(value):
    digits = re.sub(r"\\D", "", str(value or ""))
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    return digits if len(digits) == 11 and digits[0] == "7" else ""


def _passport_digits(value):
    digits = re.sub(r"\\D", "", str(value or ""))
    return digits[:10] if len(digits) >= 10 else ""


def _birth_years(value):
    """Years of the valid dates in «01.02.1985», «1.2.1985», «1985-02-01» form."""
    text, years = str(value or ""), []
    found = [(d, m, y) for d, m, y in re.findall(r"(?<!\\d)(\\d{1,2})[./-](\\d{1,2})[./-](\\d{4})(?!\\d)", text)]
    found += [(d, m, y) for y, m, d in re.findall(r"(?<!\\d)(\\d{4})[./-](\\d{1,2})[./-](\\d{1,2})(?!\\d)", text)]
    for day, month, year in found:
        try:
            time.strptime(f"{int(day):02d}.{int(month):02d}.{int(year):04d}", "%d.%m.%Y")
        except (TypeError, ValueError):
            continue
        years.append(int(year))
    return years


def _normalise_upload_line(line):
    """(«7XXXXXXXXXX паспорт», why) or (None, why it is skipped)."""
    text = str(line or "").strip()
    if not text or text.startswith("#"):
        return None, "empty"
    if text.count("|") >= 2:  # номер|паспорт|даты рождения…
        parts = text.split("|")
        phone, passport = _phone_digits(parts[0]), _passport_digits(parts[1])
        if not phone:
            return None, "phone"
        if not passport:
            return None, "passport"
        if not any(year >= 1980 for year in _birth_years("|".join(parts[2:]))):
            return None, "birth"
        return f"{phone} {passport}", "pipe"
    for sep in ("\\t", "|", ";", ","):  # the separators batch_support.load_clients reads
        if sep in text:
            first, second = text.split(sep, 1)
            break
    else:
        parts = text.split(maxsplit=1)
        first, second = parts[0], (parts[1] if len(parts) > 1 else "")
    phone, passport = _phone_digits(first), _passport_digits(second)
    if not phone:
        return None, "phone"
    if not passport:
        return None, "passport"
    return f"{phone} {passport}", "legacy"


def _prepare_uploaded_base(source, destination):
    stats = {"source": 0, "accepted": 0, "duplicates": 0, "skipped": 0, "passport": 0, "birth": 0, "phone": 0}
    rows, seen = [], set()
    for raw in Path(source).read_text("utf-8-sig", errors="replace").splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        stats["source"] += 1
        pair, reason = _normalise_upload_line(raw)
        if pair is None:
            stats["skipped"] += 1
            stats[reason] = stats.get(reason, 0) + 1
            continue
        if pair.split()[0] in seen:  # one row per number: the progress file counts numbers
            stats["duplicates"] += 1
            continue
        seen.add(pair.split()[0])
        rows.append(pair)
    if not rows:
        raise ValueError("После фильтрации не осталось подходящих строк.")
    Path(destination).write_text("\\n".join(rows) + "\\n", encoding="utf-8")
    count = _validate_base(destination)
    if count != len(rows):
        raise ValueError(f"Проверка базы вернула {count} строк вместо {len(rows)}.")
    stats["accepted"] = count
    return stats


def _filter_note(stats):
    parts = [f"{label}: {stats[key]}" for key, label in (("passport", "без паспорта"), ("birth", "не 1980+"),
                                                         ("phone", "без номера"), ("duplicates", "повторы")) if stats.get(key)]
    return ("\\n⏭ Отфильтровано " + " · ".join(parts)) if parts else ""


def _merge_clean_base(clean_path):
    """Append the new numbers of clean_path to clients.txt: (added, already there)."""
    existing = ([x.strip() for x in CLIENTS_FILE.read_text("utf-8", errors="replace").splitlines() if x.strip()]
                if CLIENTS_FILE.exists() else [])
    known = set()
    for line in existing:
        pair, _ = _normalise_upload_line(line)
        known.add(pair.split()[0] if pair else line)
    incoming = [x.strip() for x in Path(clean_path).read_text("utf-8", errors="replace").splitlines() if x.strip()]
    added = []
    for line in incoming:
        if line.split()[0] in known:
            continue
        known.add(line.split()[0])
        added.append(line)
    if added:
        merged = BASE_DIR / ".clients_merge.tmp"
        merged.write_text("\\n".join(existing + added) + "\\n", encoding="utf-8")
        merged.replace(CLIENTS_FILE)
    return len(added), len(incoming) - len(added)


def _has_unprocessed_base_rows():
    try:
        processed = {x.strip() for x in PROCESSED_FILE.read_text("utf-8", errors="replace").splitlines() if x.strip()}
    except OSError:
        processed = set()
    try:
        return any(row[1] not in processed for row in load_clients(CLIENTS_FILE))
    except Exception:
        return False


def _continue_appended_base(proc):
    """The work ended its queue while rows were added: start it again for them."""
    if not APPEND_PENDING_FILE.exists() or proc.running():
        return False
    proc.reap()
    APPEND_PENDING_FILE.unlink(missing_ok=True)
    if not _has_unprocessed_base_rows():
        return False
    ok, answer = proc.start()
    _send("➕ Очередь закончена — запускаю добавленные строки." if ok else f"⚠️ Добавленные строки ждут запуска: {answer}")
    return ok


def _download_document(file_id, destination):
'''
OLD_C_LOOP_R64 = '        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n'
NEW_C_LOOP_R64 = ('        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n'
                  '        _continue_appended_base(proc)  # BASE_TOOLS_1591R64: rows added while the work ran\n')
OLD_C_CALLBACK_R64 = ('                        if cb_chat == chat and menu.handle_callback(callback) == "upload":\n'
                      '                            waiting_upload = True\n')
NEW_C_CALLBACK_R64 = ('                        if cb_chat == chat:\n'
                      '                            menu_result = menu.handle_callback(callback)\n'
                      '                            if menu_result in ("upload", "upload_new", "upload_add"):  # BASE_TOOLS_1591R64\n'
                      '                                waiting_upload = "add" if menu_result == "upload_add" else "new"\n')
C_BUTTONS_R64 = tuple((f'                        _, answer = proc.{act}()\n',
                       '                        APPEND_PENDING_FILE.unlink(missing_ok=True)  # BASE_TOOLS_1591R64\n'
                       f'                        _, answer = proc.{act}()\n') for act in ("start", "stop", "restart"))
OLD_C_ASK_R64 = ('                        if not waiting_upload:\n'
                 '                            _send(\n'
                 '                                "Чтобы заменить базу, сначала нажми "\n'
                 '                                "«📥 Загрузить новую базу номеров»."\n'
                 '                            )\n')
NEW_C_ASK_R64 = ('                        if not waiting_upload:\n'
                 '                            _send("Сначала открой «📂 База» и выбери «➕ Добавить строки» или «🆕 Загрузить новую базу».")  # BASE_TOOLS_1591R64\n')
OLD_C_UPLOAD_R64 = '''                        was_running = proc.running()
                        tmp = BASE_DIR / ".clients_upload.tmp"
                        try:
                            _download_document(file_id, tmp)
                            count = _validate_base(tmp)

                            if was_running:
                                proc.stop()

                            _archive_progress()
                            tmp.replace(CLIENTS_FILE)

                            # New base means a new processing pass.
                            PROCESSED_FILE.unlink(missing_ok=True)

                            waiting_upload = False

                            if was_running:
                                ok, start_msg = proc.start()
                                if not ok:
                                    _send(
                                        f"✅ Новая база загружена: {count} строк.\\n"
                                        f"⚠️ Автозапуск не удался: {start_msg}"
                                    )
                                else:
                                    _send(
                                        f"✅ Новая база загружена: {count} строк.\\n"
                                        "🔄 Работавший процесс остановлен и запущен заново."
                                    )
                            else:
                                _send(
                                    f"✅ Новая база загружена: {count} строк.\\n"
                                    "Процесс оставлен остановленным. Нажми «▶️ Запустить»."
                                )
                        except Exception as exc:
                            try:
                                tmp.unlink(missing_ok=True)
                            except Exception:
                                pass
                            _send(f"❌ База не заменена: {type(exc).__name__}: {exc}")
                        continue
'''
NEW_C_UPLOAD_R64 = '''                        # BASE_TOOLS_1591R64: filter first; «add» appends without stopping, «new» replaces and starts.
                        mode = "add" if waiting_upload == "add" else "new"
                        raw_tmp = BASE_DIR / ".clients_upload.raw.tmp"
                        clean_tmp = BASE_DIR / ".clients_upload.tmp"
                        try:
                            _download_document(file_id, raw_tmp)
                            stats = _prepare_uploaded_base(raw_tmp, clean_tmp)
                            count = int(stats["accepted"])
                            waiting_upload = False
                            if mode == "add":
                                was_running = proc.running()
                                added, already = _merge_clean_base(clean_tmp)
                                if was_running and added:
                                    APPEND_PENDING_FILE.write_text(str(added), encoding="utf-8")
                                note = f"✅ Добавлено строк: {added} (после фильтрации {count} из {stats['source']})."
                                if already:
                                    note += f"\\n↩️ Уже были в базе: {already}."
                                note += _filter_note(stats)
                                note += ("\\n⚙️ Работа не остановлена: добавленные строки запустятся, когда закончится текущая очередь."
                                         if was_running and added else
                                         "\\n⏸ Процесс остановлен; строки в базе, нажми «▶️ Запустить»." if added else "")
                                _send(note)
                            else:
                                if proc.running():
                                    proc.stop()
                                _archive_progress()
                                clean_tmp.replace(CLIENTS_FILE)
                                PROCESSED_FILE.unlink(missing_ok=True)  # a new base is a new pass
                                APPEND_PENDING_FILE.unlink(missing_ok=True)
                                ok, start_msg = proc.start()
                                _send(f"✅ База загружена — {count} строк (из {stats['source']})." + _filter_note(stats)
                                      + ("\\n▶️ Новая база запущена." if ok else f"\\n⚠️ Запуск не удался: {start_msg}"))
                        except Exception as exc:
                            _send(f"❌ База не изменена: {type(exc).__name__}: {exc}")
                        finally:
                            for tmp in (raw_tmp, clean_tmp):
                                try:
                                    tmp.unlink(missing_ok=True)
                                except Exception:
                                    pass
                        continue
'''
OLD_TEST_CONTINUE_R64 = "'_restart_after_drain':lambda p:False,"
NEW_TEST_CONTINUE_R64 = "'_restart_after_drain':lambda p:False,'_continue_appended_base':lambda p:False,"
README_NOTE_R64 = ('\n\nРЕВИЗИЯ 64 (fix_package_1591.py)\nКнопки «📂 База» и «🔢 Генерация» (впервые выложены вручную как r63, теперь собираются здесь).\n'
                   '«📂 База» → «➕ Добавить строки» (дописывает к базе, работа не останавливается, добавленные строки\n'
                   'запускаются после текущей очереди) или «🆕 Загрузить новую базу» (останавливает, заменяет, запускает). Файл\n'
                   'фильтруется: строки «номер|паспорт|даты рождения» — нужен паспорт (10 цифр) и год рождения 1980+ (из\n'
                   'нескольких дат хватит одной); строки старого формата (номер и паспорт через пробел, таб, |, ; или ,) —\n'
                   'нужен паспорт; повторы номеров убираются. Ответ: сколько строк осталось и сколько и почему отфильтровано.\n'
                   '«🔢 Генерация»: первые 7 цифр (+7900111****, по одному в строке) → .txt со всеми 10 000 номерами.\n'
                   'Маркер: BASE_TOOLS_1591R64.\n')

# Revision 65: the menu only. A setting restarted the bot from inside the button's handler, before the controller
# saved the update offset; Telegram delivered the same button after the start and the bot restarted forever. The
# restart now runs from tick() a moment later, and a value already in effect restarts nothing.
SETTING_RESTART_MARKER = "SETTING_RESTART_1591R65"
OLD_SETTING_RESTART_MARK_R65 = NEW_BASE_TOOLS_MARK_R64.splitlines(keepends=True)[-1]
NEW_SETTING_RESTART_MARK_R65 = (OLD_SETTING_RESTART_MARK_R65
                                + '# SETTING_RESTART_1591R65: «⚙️ Настройки» restart the bot once, after the button is acknowledged.\n')
README_NOTE_R65 = ('\n\nРЕВИЗИЯ 65 (fix_package_1591.py)\nТолько меню. Смена тарифа (и браузеров, вкладок, DeepSeek) в «⚙️ Настройки» перезапускала бота\n'
                   'бесконечно: перезапуск шёл прямо из обработки кнопки, бот не успевал отметить её обработанной, и после\n'
                   'запуска Telegram присылал ту же кнопку снова. Теперь перезапуск идёт через пару секунд, когда кнопка уже\n'
                   'отмечена, а если выбранное значение уже стоит — перезапуска нет. Маркер: SETTING_RESTART_1591R65.\n')

# Revision 66: the menu only. eSIMs made more than 5 days ago leave «Мои eSIM» (and the counters, export, link
# checks) by themselves; the result files on the server stay.
AUTO_EXPIRE_MARKER = "AUTO_EXPIRE_1591R66"
OLD_AUTO_EXPIRE_MARK_R66 = NEW_SETTING_RESTART_MARK_R65.splitlines(keepends=True)[-1]
NEW_AUTO_EXPIRE_MARK_R66 = (OLD_AUTO_EXPIRE_MARK_R66
                            + '# AUTO_EXPIRE_1591R66: «Мои eSIM» keeps the last 5 days; older eSIMs leave the list by themselves.\n')
README_NOTE_R66 = ('\n\nРЕВИЗИЯ 66 (fix_package_1591.py)\nТолько меню. eSIM старше 5 дней сами уходят из «📱 Мои eSIM», из счётчиков «Ждут оплаты / Готово»,\n'
                   'из выгрузки и проверки ссылок. Файлы результатов на сервере остаются. Маркер: AUTO_EXPIRE_1591R66.\n')

# Revision 67: the registration flow after the owner's data.
# - REENTER_ROW_1591R67: /registration/error saying «введите данные снова» (the order is kept, the data is asked
#   again; it follows «Отправить снова» 9 times out of 10) or showing the order's first steps («выбрать способ
#   регистрации», the order reset after signing) restarts the same row in a fresh page — the client gets a new
#   request — at most twice per row; then the old rule (skip) applies. A named refusal is still skipped at once.
# - SIGN_THROTTLE_1591R67: «Подписать договор» is not clicked again every ~11 s while the page stays: after a click
#   the site accepted the next waits 60 s, at most 3 clicks per row; 3 minutes after the last one the row is
#   recorded as unverified (❔) instead of waiting in silence.
# - SIGN_STEPS_1591R67: DeepSeek is told that the steps page («несколько шагов… выбрать способ регистрации») is the
#   order's start, not the payment; the payment is only «теперь пора оплатить eSIM».
REENTER_MARKER = "REENTER_ROW_1591R67"
OLD_REENTER_MARK_R67 = NEW_AUTO_EXPIRE_MARK_R66.splitlines(keepends=True)[-1]
NEW_REENTER_MARK_R67 = (OLD_REENTER_MARK_R67
                        + '# REENTER_ROW_1591R67: «введите данные снова» re-enters the row; «Подписать» is not clicked in a loop.\n')
OLD_REENTER_HEAD_R67 = ('def enter_error_guard(worker, note):\n'
                        '    # ERROR_SKIP_ALWAYS_1591R16: every /registration/error after the confirmation is handled\n')
NEW_REENTER_HEAD_R67 = ('''# REENTER_ROW_1591R67
REENTER_ROW_MAX_1591R67 = 2
_REENTER_TEXTS_1591R67 = ("введите данные снова", "заново ввести данные", "выбрать способ регистрации",
                          "выберите способ регистрации")


def _reenter_page_1591r67(page):
    """The phrase that says the order is kept and the data is asked again, "" when none."""
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower().replace("\\xa0", " ")
    except Exception:
        return ""
    return next((text for text in _REENTER_TEXTS_1591R67 if text in body), "")


def _reenter_row_1591r67(worker):
    """«Введите данные снова» (or the order back at its first step): the same row starts over in a fresh
    page and the client gets a new request, at most REENTER_ROW_MAX_1591R67 times per row."""
    hint = _reenter_page_1591r67(worker.get("page"))
    if not hint:
        return False
    key = _error_row_key(worker)
    used = int((worker.get("reenter_1591r67") or {}).get(key) or 0)
    if used >= REENTER_ROW_MAX_1591R67:
        return False
    worker["reenter_1591r67"] = {key: used + 1}
    print(
        f"[Вкладка {worker['id']}] /registration/error: «{hint}». Заказ жив — ввожу данные заново "
        f"({used + 1}/{REENTER_ROW_MAX_1591R67}), строка {key} не пропускается.",
        flush=True,
    )
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    set_tab_status(worker, "♻️", f"Сайт просит ввести данные снова — повторяю строку ({used + 1}/{REENTER_ROW_MAX_1591R67}).")
    external_heartbeat(worker, "reenter_row_1591r67")
    return True


# SIGN_THROTTLE_1591R67
SIGN_RECLICK_SECONDS_1591R67 = 60
SIGN_CLICKS_MAX_1591R67 = 3


def _sign_hold_1591r67(base_dir, worker):
    """True while the last «Подписать договор» is still being answered: after a click the site accepted
    the next one waits SIGN_RECLICK_SECONDS_1591R67, a row gets at most SIGN_CLICKS_MAX_1591R67 clicks, and
    UNVERIFIED_HOLD_SECONDS after the last one the row is recorded as unverified. r66 clicked every ~11 s
    while the page stayed and the order could be reset."""
    key = f"{_error_row_key(worker)}:{worker.get('generation')}"  # a re-entered row starts its count anew
    state = worker.get("sign_clicks_1591r67") or {}
    if state.get("row") != key:
        state = {"row": key, "n": 0, "at": 0.0}
        worker["sign_clicks_1591r67"] = state
    now = monotonic()
    if not state["n"]:
        state.update(n=1, at=now)
        return False
    wait = SIGN_RECLICK_SECONDS_1591R67 if _sign_went_through_1591r37(worker) else 12
    if state["n"] < SIGN_CLICKS_MAX_1591R67 and now - state["at"] >= wait:
        state.update(n=state["n"] + 1, at=now)
        return False
    if state["n"] >= SIGN_CLICKS_MAX_1591R67 and now - state["at"] >= UNVERIFIED_HOLD_SECONDS:
        _finish_unverified_1591r24(
            base_dir, worker,
            f"после {state['n']} нажатий «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не изменилась",
        )
        return True
    worker["phase"] = "SUCCESS_ASSIST"
    set_tab_status(worker, "⏳", f"Подпись отправлена ({state['n']}/{SIGN_CLICKS_MAX_1591R67}) — жду ответа сайта, "
                                 "повторно не нажимаю.")
    return True

def enter_error_guard(worker, note):
    # ERROR_SKIP_ALWAYS_1591R16: every /registration/error after the confirmation is handled
''')
OLD_REENTER_CALL_R67 = ('    reason = _error_page_final_reason(worker.get("page")) or "registration/error после подтверждения"\n'
                        '    if _error_skip_final(worker, reason):\n')
NEW_REENTER_CALL_R67 = ('    reason = _error_page_final_reason(worker.get("page")) or "registration/error после подтверждения"\n'
                        '    if reason == "registration/error после подтверждения" and _reenter_row_1591r67(worker):  # REENTER_ROW_1591R67\n'
                        '        return\n'
                        '    if _error_skip_final(worker, reason):\n')
OLD_SIGN_CALL_R67 = ('        try:\n'
                     '            set_tab_status(\n'
                     '                worker, "✍️",\n'
                     '                "Подтверждение успешно. Заполняю подпись и подписываю договор."\n')
NEW_SIGN_CALL_R67 = ('        if _sign_hold_1591r67(base_dir, worker):  # SIGN_THROTTLE_1591R67: the site is still answering\n'
                     '            return\n'
                     '        try:\n'
                     '            set_tab_status(\n'
                     '                worker, "✍️",\n'
                     '                "Подтверждение успешно. Заполняю подпись и подписываю договор."\n')
OLD_SIGN_STEPS_R67 = ('        "«VERDICT: PAYMENT» или «VERDICT: NOT_SIGNED». "\n')
NEW_SIGN_STEPS_R67 = ('        "«VERDICT: PAYMENT» или «VERDICT: NOT_SIGNED». "\n'
                      '        "Оплата — это ТОЛЬКО экран «Теперь пора оплатить eSIM». Страница со списком шагов «подтвердите данные → "  # SIGN_STEPS_1591R67\n'
                      '        "оплатите картой → дождитесь регистрации договора» и кнопкой «выбрать способ регистрации» — это НАЧАЛО "\n'
                      '        "заказа (сайт сбросил оформление), а не оплата: итог «Не подписано — сайт вернул заказ в начало», VERDICT: NOT_SIGNED. "\n')
README_NOTE_R67 = ('\n\nРЕВИЗИЯ 67 (fix_package_1591.py)\nРегистрация. «Введите данные снова» на /registration/error (так сайт отвечает почти каждый раз после\n'
                   '«Отправить снова») и сброс заказа в начало после подписи («выбрать способ регистрации») больше не\n'
                   'выбрасывают строку: та же строка начинается заново в новой вкладке, клиент получает новый запрос; не\n'
                   'больше 2 раз на строку, потом прежнее правило (пропуск). «Подписать договор» больше не нажимается каждые\n'
                   '11 секунд: после принятой сайтом подписи следующее нажатие через 60 секунд, не больше 3 на строку, через\n'
                   '3 минуты после последнего строка отмечается «❔ подпись не подтверждена» (с сообщением), а не висит молча.\n'
                   'DeepSeek знает, что страница со списком шагов — начало заказа, а не оплата. Маркер: REENTER_ROW_1591R67.\n')

# Revision 68: the site takes the signature (checksignature 200), then answers the passport step with 412
# PERSONAL_TOKEN_ERROR and asks for the data again («введите данные снова — с заказом всё хорошо»). All six
# «❔ подпись не подтверждена» of a server in three days were this. The row now starts over (a new request to
# the client, the confirmation token is renewed) instead of being recorded as unverified, at most twice per row
# (REENTER_ROW_MAX_1591R67 shared with r67).
TOKEN_REENTER_MARKER = "TOKEN_REENTER_1591R68"
OLD_TOKEN_MARK_R68 = NEW_REENTER_MARK_R67.splitlines(keepends=True)[-1]
NEW_TOKEN_MARK_R68 = (OLD_TOKEN_MARK_R68
                      + '# TOKEN_REENTER_1591R68: 412 PERSONAL_TOKEN_ERROR after the signature re-enters the row, no ❔.\n')
OLD_TOKEN_DEF_R68 = 'def _reenter_row_1591r67(worker):\n'
NEW_TOKEN_DEF_R68 = 'def _reenter_row_1591r67(worker, forced=""):\n'
OLD_TOKEN_HINT_R68 = '    hint = _reenter_page_1591r67(worker.get("page"))\n'
NEW_TOKEN_HINT_R68 = '    hint = _reenter_page_1591r67(worker.get("page")) or forced  # TOKEN_REENTER_1591R68: the site\'s own code\n'
OLD_TOKEN_FINISH_R68 = ('def _finish_unverified_1591r24(base_dir, worker, reason):\n'
                        '    """The signing could not be confirmed: record it apart from the successes and stop the tab."""\n')
NEW_TOKEN_FINISH_R68 = ('def _finish_unverified_1591r24(base_dir, worker, reason):\n'
                        '    """The signing could not be confirmed: record it apart from the successes and stop the tab."""\n'
                        '    # TOKEN_REENTER_1591R68: the site took the signature, then refused the confirmation token (412\n'
                        '    # PERSONAL_TOKEN_ERROR) or asks for the data again; the order is kept, so the row starts over\n'
                        '    # (a new request to the client) instead of being recorded as unverified.\n'
                        '    if _reenter_row_1591r67(worker, "PERSONAL_TOKEN_ERROR" if "PERSONAL_TOKEN" in str(reason) else ""):\n'
                        '        return None\n')
README_NOTE_R68 = ('\n\nРЕВИЗИЯ 68 (fix_package_1591.py)\nСайт принимает подпись (checksignature 200), а на шаге паспортных данных отвечает 412\n'
                   'PERSONAL_TOKEN_ERROR и просит «ввести данные снова — с заказом всё хорошо». Все «❔ подпись не подтверждена»\n'
                   'были такими. Теперь строка начинается заново (клиент получает новый запрос, токен обновляется), а не\n'
                   'записывается как «❔»; не больше 2 повторов на строку. Маркер: TOKEN_REENTER_1591R68.\n')

# Revision 69: a faster row flow, from a bot that does the same registration.
# - ORDER_REUSE_1591R69: the order link («/registration/esim?hash_order=…», captured after «идём дальше») is kept
#   per tab for 23 hours. A fresh tab opens it instead of the basket (tariff, contact phone, «идём дальше»: 1–2
#   minutes) and goes straight to «выбрать способ регистрации» → «с сим билайна». The link is dropped when its client
#   confirmed (the order is taken), when the form does not open by it, after 3 opens without a confirmation, or
#   when the tariff changed. BEELINE_ORDER_REUSE=0 turns it off.
# - GREY_SAME_FORM_1591R69: a grey «Продолжить» takes the next row in the same form (fields cleared) instead of
#   a fresh tab for the retry and another for the next row; only 3 greys in a row in one page retry the row in
#   a fresh tab (the form itself may be stale, r22). BEELINE_GREY_SAME_FORM=0 restores r22.
# - CORPORATE_1591R69: «с корпоративным номером не получится» skips the row at once («указать личный номер»,
#   the next row in the same form) instead of 3 restarts through the basket and a deferral.
# - MOBILE_PROXY_1591R69: «⚙️ Настройки → 📶 Мобильный прокси» (off by default): the browser contexts go through
#   the proxy, and «что-то пошло не так» calls the proxy's IP change link (once per page, 90 s apart).
# - «получить новый запрос» is a resend button too. BASE_STRICT_1591R69: an uploaded «номер|паспорт|даты» line
#   needs exactly one birth date, 1982 or later (BEELINE_BIRTH_YEAR_MIN).
ORDER_REUSE_MARKER = "ORDER_REUSE_1591R69"
OLD_ORDER_MARK_R69 = NEW_TOKEN_MARK_R68.splitlines(keepends=True)[-1]
NEW_ORDER_MARK_R69 = (OLD_ORDER_MARK_R69
                      + '# ORDER_REUSE_1591R69: new tabs reuse the order link; grey rows stay in the form; corporate rows skip.\n')
OLD_ORDER_HEAD_R69 = '# REENTER_ROW_1591R67\nREENTER_ROW_MAX_1591R67 = 2\n'
NEW_ORDER_HEAD_R69 = r'''# ORDER_REUSE_1591R69
ORDER_REUSE_1591R69 = str(os.environ.get("BEELINE_ORDER_REUSE") or "1").strip().lower() not in {"0", "off", "no", "false"}
ORDER_LINK_MAX_AGE_1591R69 = 23 * 3600   # the order link lives about a day
ORDER_OPENS_MAX_1591R69 = 3              # opens in a row that never reached the confirmation
ORDER_LINKS_DIR_1591R69 = "order_links"
_ORDER_TAKEN_PHASES_1591R69 = {"POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST", "SUCCESS_STOP"}


def _order_file_1591r69(base_dir, tab_id):
    return Path(base_dir or Path(__file__).resolve().parent) / ORDER_LINKS_DIR_1591R69 / f"tab_{tab_id}.json"


def _read_order_1591r69(path):
    try:
        rec = json.loads(Path(path).read_text("utf-8"))
    except Exception:
        return None
    return rec if isinstance(rec, dict) and rec.get("url") else None


def _write_order_1591r69(path, rec):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False), "utf-8")
    tmp.replace(path)


def _remember_order_1591r69(page, phone, digits):
    """The basket path just captured the order page: this tab keeps its link for the next fresh tabs."""
    store = getattr(page, "_order_store_1591r69", None)
    url = str(getattr(page, "_reserved_sim_url", "") or "")
    if not ORDER_REUSE_1591R69 or not store or "/registration" not in urlsplit(url).path:
        return False
    base_dir, tab_id = store
    try:
        _write_order_1591r69(_order_file_1591r69(base_dir, tab_id), {
            "url": url, "sim_number": getattr(page, "_reserved_sim_number", None), "contact_phone": phone,
            "contact_digits": digits, "tariff": TARIFF_NAME, "created": time.time(), "opens": 0})
    except Exception as exc:
        print(f"[Вкладка {tab_id}] Ссылку заказа сохранить не удалось: {type(exc).__name__}: {exc}", flush=True)
        return False
    print(f"[Вкладка {tab_id}] Заказ сохранён: новые вкладки откроют его сразу, без корзины.", flush=True)
    return True


def _forget_order_1591r69(worker, why):
    path = _order_file_1591r69(worker.get("base_dir"), worker.get("id"))
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except Exception:
        return False
    print(f"[Вкладка {worker.get('id')}] Сохранённый заказ больше не используется: {why}.", flush=True)
    return True


def _visible_1591r69(locator):
    try:
        return locator.count() > 0 and locator.is_visible()
    except Exception:
        return False


def _order_to_form_1591r69(page, timeout=30):
    """From the order page to the «с сим билайна» form: True when the active-number field is shown."""
    form = page.locator('input[name="ctn"]').first
    method = page.get_by_role("button", name=re.compile(r"выбрать способ регистрации", re.I)).first
    chips = (page.locator("div").filter(
                 has_text=re.compile(r"^с сим билайнавозьмём ваши данные с активного номера у нас$")).nth(1),
             page.get_by_text(re.compile(r"^\s*с\s+(?:сим|sim)\s+билайна\s*$", re.I)).first)
    clicks = {"method": 0, "chip": 0}
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if _visible_1591r69(form):
            return True
        _row_progress(page, "открываю форму по сохранённому заказу")
        chip = next((c for c in chips if _visible_1591r69(c)), None)
        try:
            if chip is not None and clicks["chip"] < 3:
                clicks["chip"] += 1
                chip.click(timeout=5000, no_wait_after=True)
                page.wait_for_timeout(1500)
                continue
            if _visible_1591r69(method) and clicks["method"] < 3:
                clicks["method"] += 1
                method.scroll_into_view_if_needed(timeout=3000)
                method.click(timeout=5000)
                page.wait_for_timeout(1500)
                continue
        except Exception:
            pass
        page.wait_for_timeout(500)
    return _visible_1591r69(form)


def _reuse_order_1591r69(worker):
    """A fresh tab opens this tab's saved order instead of the basket. False (the basket path follows) when
    there is none, it is stale, or the form does not open by it (the link is dropped then)."""
    if not ORDER_REUSE_1591R69:
        return False
    page, diagnostic, tab_id = worker["page"], worker.get("diagnostic"), worker.get("id")
    path = _order_file_1591r69(worker.get("base_dir"), tab_id)
    rec = _read_order_1591r69(path)
    if rec is None:
        return False
    age = time.time() - float(rec.get("created") or 0)
    if age > ORDER_LINK_MAX_AGE_1591R69 or age < 0:
        _forget_order_1591r69(worker, "ссылке больше 23 часов")
        return False
    if int(rec.get("opens") or 0) >= ORDER_OPENS_MAX_1591R69:
        _forget_order_1591r69(worker, f"{ORDER_OPENS_MAX_1591R69} открытия подряд без подтверждения")
        return False
    if str(rec.get("tariff") or "") != TARIFF_NAME:
        _forget_order_1591r69(worker, "тариф сменился")
        return False
    rec["opens"] = int(rec.get("opens") or 0) + 1
    try:
        _write_order_1591r69(path, rec)
    except Exception:
        pass
    print(f"[Вкладка {tab_id}] Открываю сохранённый заказ без корзины (ему {int(age // 60)} мин).", flush=True)
    _row_progress(page, "открываю сохранённый заказ")
    opened, error = False, ""
    try:
        page.goto(rec["url"], wait_until="domcontentloaded", timeout=45000)
        ensure_region_page(page, diagnostic)
        opened = _order_to_form_1591r69(page)
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    if not opened:
        try:
            diagnostic.snapshot("order_reuse_failed")
            diagnostic.write("order_reuse_failed", url=rec["url"], error=error)
        except Exception:
            pass
        _forget_order_1591r69(worker, "форма по ссылке не открылась" + (f" ({error})" if error else ""))
        return False
    setattr(page, "_reserved_sim_url", rec["url"])
    setattr(page, "_reserved_sim_url_locked", True)
    if rec.get("sim_number"):
        setattr(page, "_reserved_sim_number", rec["sim_number"])
    if rec.get("contact_digits") and rec.get("contact_phone"):
        worker["contact_digits"], worker["contact_phone"] = rec["contact_digits"], rec["contact_phone"]
    try:
        diagnostic.write("order_reused", url=rec["url"], age_seconds=int(age), opens=rec["opens"])
    except Exception:
        pass
    print(f"[Вкладка {tab_id}] Форма открыта по сохранённому заказу.", flush=True)
    return True


def _order_reached_auth_1591r69(worker):
    """The confirmation started on this order: its open counter starts over."""
    path = _order_file_1591r69(worker.get("base_dir"), worker.get("id"))
    rec = _read_order_1591r69(path)
    if rec is not None and rec.get("opens"):
        rec["opens"] = 0
        try:
            _write_order_1591r69(path, rec)
        except Exception:
            pass


# GREY_SAME_FORM_1591R69
GREY_SAME_FORM_1591R69 = str(os.environ.get("BEELINE_GREY_SAME_FORM") or "1").strip().lower() not in {"0", "off", "no", "false"}
GREY_STREAK_MAX_1591R69 = 3


def _grey_streak_1591r69(worker):
    """True when the grey row is retried in a fresh tab (r22): after GREY_STREAK_MAX_1591R69 greys in a row in
    one page, when the form itself may be stale. Otherwise the next row goes into the same form."""
    if not GREY_SAME_FORM_1591R69:
        return True
    gen = worker.get("generation")
    seen_gen, count = worker.get("grey_streak_1591r69") or (gen, 0)
    count = (count if seen_gen == gen else 0) + 1
    if count >= GREY_STREAK_MAX_1591R69:
        worker["grey_streak_1591r69"] = None
        print(f"[Вкладка {worker.get('id')}] {count} серых «Продолжить» подряд — возможно, зависла сама форма; "
              "эту строку повторяю в новой вкладке.", flush=True)
        return True
    worker["grey_streak_1591r69"] = (gen, count)
    return False


# CORPORATE_1591R69
_CORPORATE_TEXTS_1591R69 = ("с корпоративным номером не получится", "корпоративным номером не получится")
_PAGE_CHECK_PHASES_1591R69 = {"AUTH_WAIT", "CONFIRM", "RESEND"}


def _corporate_row_1591r69(base_dir, worker):
    """Mobile ID does not work for a corporate number: the row is skipped at once and the next one goes into
    the form «указать личный номер» opens (or a fresh start when it does not)."""
    page, tab_id, key = worker["page"], worker.get("id"), _error_row_key(worker)
    capture_blackbox(worker, "corporate_number")
    print(f"[Вкладка {tab_id}] Строка {key}: сайт пишет «с корпоративным номером не получится» — "
          "пропускаю её и беру следующую.", flush=True)
    clicked = False
    for locator in (page.get_by_role("button", name=re.compile(r"указать\s+личный\s+номер", re.I)),
                    page.get_by_text(re.compile(r"^\s*указать\s+личный\s+номер\s*$", re.I))):
        try:
            if locator.count() and locator.first.is_visible():
                locator.first.click(timeout=5000)
                clicked = True
                break
        except Exception:
            continue
    event = worker.get("launch_ready_event")
    if event is not None and not event.is_set():
        event.set()
    save_worker_result(base_dir, worker, "CORPORATE_NUMBER")
    remember_processed_number(base_dir, worker.get("row"))
    form_ok = False
    deadline = monotonic() + (10 if clicked else 0)
    while monotonic() < deadline:
        if _visible_1591r69(page.locator('input[name="ctn"]').first):
            form_ok = True
            break
        page.wait_for_timeout(300)
    if form_ok:
        clear_registration_fields(page)
    reset_runtime_state(worker)
    worker["grey_streak_1591r69"] = None
    worker["form_ready"] = form_ok
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key}: корпоративный номер — пропущена")
    external_heartbeat(worker, "corporate_number")
    return True


# MOBILE_PROXY_1591R69
IP_CHANGE_COOLDOWN_1591R69 = 90
_IP_CHANGE_TEXTS_1591R69 = ("что-то пошло не так", "что то пошло не так", "еще раз нажать, и все заработает")


def _parse_proxy_1591r69(raw):
    """«scheme://» (http, https, socks5; http by default), the login and password before «@» or after the port
    («host:port:login:pass»), → Playwright's proxy dict, or None."""
    text = str(raw or "").strip()
    if not text:
        return None
    scheme = "http"
    if "://" in text:
        scheme, text = text.split("://", 1)
        scheme = scheme.lower()
    if scheme not in {"http", "https", "socks5"}:
        return None
    user = password = ""
    if "@" in text:
        cred, text = text.rsplit("@", 1)
        user, _, password = cred.partition(":")
    parts = text.strip("/").split(":")
    if len(parts) == 4 and not user:
        parts, user, password = parts[:2], parts[2], parts[3]
    if len(parts) != 2 or not parts[0] or not parts[1].isdigit():
        return None
    proxy = {"server": f"{scheme}://{parts[0]}:{parts[1]}"}
    if user:
        proxy.update({"username": user, "password": password})
    return proxy


def _mobile_proxy_1591r69():
    """(Playwright proxy or None, IP change link or "") from «📶 Мобильный прокси»; both off unless enabled."""
    if str(os.environ.get("BEELINE_MOBILE_PROXY_ON") or "0").strip().lower() not in {"1", "on", "yes", "true"}:
        return None, ""
    return (_parse_proxy_1591r69(os.environ.get("BEELINE_MOBILE_PROXY")),
            str(os.environ.get("BEELINE_IP_CHANGE_URL") or "").strip())


def _proxy_context_kwargs_1591r69(tab_id):
    proxy, _ = _mobile_proxy_1591r69()
    if not proxy:
        return {}
    print(f"[Вкладка {tab_id}] 📶 Браузер работает через мобильный прокси {proxy['server']}.", flush=True)
    return {"proxy": proxy}


def _change_ip_1591r69(worker, why):
    """Call the proxy's IP change link (in the background), at most once per IP_CHANGE_COOLDOWN_1591R69 for
    all tabs. The link itself is never printed: it carries the proxy key."""
    _, url = _mobile_proxy_1591r69()
    if not url.startswith(("http://", "https://")):
        return False
    tab_id = worker.get("id")
    stamp = Path(worker.get("base_dir") or Path(__file__).resolve().parent) / "ip_change.json"
    try:
        last = float(json.loads(stamp.read_text("utf-8")).get("at") or 0)
    except Exception:
        last = 0.0
    if time.time() - last < IP_CHANGE_COOLDOWN_1591R69:
        return False
    try:
        stamp.write_text(json.dumps({"at": time.time(), "tab": tab_id, "why": why}, ensure_ascii=False), "utf-8")
    except Exception:
        pass
    import threading

    def _call():
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                code = response.status
            print(f"[Вкладка {tab_id}] 📶 Смена IP: ответ {code}.", flush=True)
        except Exception as exc:
            print(f"[Вкладка {tab_id}] 📶 Смена IP не удалась: {type(exc).__name__}: {str(exc)[:200]}", flush=True)

    threading.Thread(target=_call, daemon=True).start()
    print(f"[Вкладка {tab_id}] 📶 На странице «{why}» — меняю IP мобильного прокси.", flush=True)
    return True


def _row_tick_1591r69(base_dir, worker):
    """Before the phase handlers: the order link is dropped once its client confirmed, a corporate number ends
    the row, «что-то пошло не так» changes the IP when «📶 Мобильный прокси» is on. True when the row ended."""
    phase, gen = worker.get("phase"), worker.get("generation")
    if phase in _ORDER_TAKEN_PHASES_1591R69 and worker.get("order_taken_1591r69") != gen:
        worker["order_taken_1591r69"] = gen
        _forget_order_1591r69(worker, "клиент подтвердил вход — заказ занят этой строкой")
    if phase == "CONFIRM" and worker.get("order_auth_1591r69") != gen:
        worker["order_auth_1591r69"] = gen
        _order_reached_auth_1591r69(worker)
    if phase not in _PAGE_CHECK_PHASES_1591R69 | {"POST_AUTH_REVIEW", "ERROR_ASSIST"}:
        return False
    now = monotonic()
    if now - float(worker.get("page_check_at_1591r69") or 0) < 2:
        return False
    worker["page_check_at_1591r69"] = now
    page = worker.get("page")
    try:
        if page is None or page.is_closed():
            return False
        body = (page.locator("body").inner_text(timeout=1000) or "").lower().replace("ё", "е")
    except Exception:
        return False
    if phase in _PAGE_CHECK_PHASES_1591R69 and any(text in body for text in _CORPORATE_TEXTS_1591R69):
        return _corporate_row_1591r69(base_dir, worker)
    if worker.get("ip_changed_1591r69") != gen:
        hit = next((text for text in _IP_CHANGE_TEXTS_1591R69 if text in body), "")
        if hit and _change_ip_1591r69(worker, hit):
            worker["ip_changed_1591r69"] = gen
    return False


''' + OLD_ORDER_HEAD_R69
OLD_ORDER_TICK_R69 = 'def tick_worker(base_dir, worker):\n    if worker["phase"] == "POST_CONTINUE":\n'
NEW_ORDER_TICK_R69 = ('def tick_worker(base_dir, worker):\n'
                      '    if _row_tick_1591r69(base_dir, worker):  # ORDER_REUSE_1591R69, CORPORATE_1591R69, MOBILE_PROXY_1591R69\n'
                      '        return\n'
                      '    if worker["phase"] == "POST_CONTINUE":\n')
OLD_ORDER_START_R69 = ('    if not worker["form_ready"]:\n'
                       '        worker["contact_digits"] = "791900011" + f"{secrets.randbelow(100):02d}"\n'
                       '        digits = worker["contact_digits"]\n'
                       '        worker["contact_phone"] = (\n'
                       '            f"+7 {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:11]}"\n'
                       '        )\n')
NEW_ORDER_START_R69 = (OLD_ORDER_START_R69
                       + '    # ORDER_REUSE_1591R69: a fresh tab opens this tab\'s saved order instead of the basket.\n'
                       '    setattr(page, "_order_store_1591r69", (base_dir, tab_id))\n'
                       '    worker.setdefault("base_dir", base_dir)\n'
                       '    worker.setdefault("base_dir", base_dir)\n'
                       '    if not worker["form_ready"] and _reuse_order_1591r69(worker):\n'
                       '        worker["form_ready"] = True\n')
OLD_ORDER_SAVE_R69 = ('        capture_esim_offer_page(\n'
                      '            page,\n'
                      '            diagnostic=diagnostic,\n'
                      '            contact_phone=phone,\n'
                      '            timeout=6,\n'
                      '        )\n')
NEW_ORDER_SAVE_R69 = OLD_ORDER_SAVE_R69 + '        _remember_order_1591r69(page, phone, digits)  # ORDER_REUSE_1591R69\n'
OLD_GREY_RETRY_R69 = ('    if status == "INVALID_ROW" and _invalid_row_retry_1591r22(worker):  # ROW_SKIP_PERSIST_1591R22\n'
                      '        return\n')
NEW_GREY_RETRY_R69 = ('    # GREY_SAME_FORM_1591R69: a grey row is retried in a fresh tab only after a streak of them\n'
                      '    if status == "INVALID_ROW" and _grey_streak_1591r69(worker) and _invalid_row_retry_1591r22(worker):  # ROW_SKIP_PERSIST_1591R22\n'
                      '        return\n'
                      '    if status != "INVALID_ROW":\n'
                      '        worker["grey_streak_1591r69"] = None\n')
OLD_GREY_NEXT_R69 = '        if _fresh_tab_for_next_row_1591r22(worker):\n            return\n'
NEW_GREY_NEXT_R69 = ('        if not GREY_SAME_FORM_1591R69 and _fresh_tab_for_next_row_1591r22(worker):  # GREY_SAME_FORM_1591R69\n'
                     '            return\n')
OLD_RESEND_LABEL_R69 = '        r"^\\s*(?:отправить\\s+снова|отправить|повторить\\s+ещ[её])\\s*$",\n'
NEW_RESEND_LABEL_R69 = ('        r"^\\s*(?:отправить\\s+снова|отправить|повторить\\s+ещ[её]|получить\\s+новый\\s+запрос)\\s*$",'
                        '  # ORDER_REUSE_1591R69: «получить новый запрос»\n')
OLD_PROXY_CTX_R69 = '        context = browser.new_context(no_viewport=True)\n'
NEW_PROXY_CTX_R69 = '        context = browser.new_context(no_viewport=True, **_proxy_context_kwargs_1591r69(tab_id))  # MOBILE_PROXY_1591R69\n'
ORDER_EDITS_R69 = ((OLD_ORDER_MARK_R69, NEW_ORDER_MARK_R69, "order reuse: marker"),
                   (OLD_ORDER_HEAD_R69, NEW_ORDER_HEAD_R69, "order reuse: helpers"),
                   (OLD_ORDER_TICK_R69, NEW_ORDER_TICK_R69, "order reuse: tick hook"),
                   (OLD_ORDER_START_R69, NEW_ORDER_START_R69, "order reuse: fresh tab opens the order"),
                   (OLD_ORDER_SAVE_R69, NEW_ORDER_SAVE_R69, "order reuse: the basket path saves the order"),
                   (OLD_GREY_RETRY_R69, NEW_GREY_RETRY_R69, "grey rows: streak before a fresh tab"),
                   (OLD_GREY_NEXT_R69, NEW_GREY_NEXT_R69, "grey rows: the next row in the same form"),
                   (OLD_RESEND_LABEL_R69, NEW_RESEND_LABEL_R69, "resend: «получить новый запрос»"),
                   (OLD_PROXY_CTX_R69, NEW_PROXY_CTX_R69, "mobile proxy: browser context"))
# BASE_STRICT_1591R69 (controller): exactly one birth date, BEELINE_BIRTH_YEAR_MIN (1982) or later.
BASE_STRICT_MARKER = "BASE_STRICT_1591R69"
OLD_C_BIRTH_R69 = ('        if not any(year >= 1980 for year in _birth_years("|".join(parts[2:]))):\n'
                   '            return None, "birth"\n')
NEW_C_BIRTH_R69 = ('        # BASE_STRICT_1591R69: exactly one birth date, BIRTH_YEAR_MIN or later; several dates are skipped\n'
                   '        years = _birth_years("|".join(parts[2:]))\n'
                   '        if len(years) > 1:\n'
                   '            return None, "dates"\n'
                   '        if not years or years[0] < BIRTH_YEAR_MIN:\n'
                   '            return None, "birth"\n')
OLD_C_BIRTH_YEARS_R69 = 'def _birth_years(value):\n    """Years of the valid dates in «01.02.1985», «1.2.1985», «1985-02-01» form."""\n'
NEW_C_BIRTH_YEARS_R69 = ('BIRTH_YEAR_MIN = int(os.environ.get("BEELINE_BIRTH_YEAR_MIN") or 1982)  # BASE_STRICT_1591R69\n\n\n'
                         'def _birth_years(value):\n'
                         '    """Years of the valid dates in «01.02.1985», «1.2.1985», «1985-02-01» form (one per distinct date)."""\n')
OLD_C_BIRTH_RET_R69 = '        years.append(int(year))\n    return years\n'
NEW_C_BIRTH_RET_R69 = ('        if (int(day), int(month), int(year)) not in seen:  # BASE_STRICT_1591R69: a repeated date is one date\n'
                       '            seen.add((int(day), int(month), int(year)))\n'
                       '            years.append(int(year))\n'
                       '    return years\n')
OLD_C_BIRTH_INIT_R69 = '    text, years = str(value or ""), []\n'
NEW_C_BIRTH_INIT_R69 = '    text, years, seen = str(value or ""), [], set()\n'
OLD_C_NOTE_R69 = '    parts = [f"{label}: {stats[key]}" for key, label in (("passport", "без паспорта"), ("birth", "не 1980+"),\n'
NEW_C_NOTE_R69 = ('    parts = [f"{label}: {stats[key]}" for key, label in (("passport", "без паспорта"),\n'
                  '                                                         ("birth", f"не {BIRTH_YEAR_MIN}+"), ("dates", "несколько дат"),\n')
C_EDITS_R69 = ((OLD_C_BIRTH_YEARS_R69, NEW_C_BIRTH_YEARS_R69, "controller: birth year minimum"),
               (OLD_C_BIRTH_INIT_R69, NEW_C_BIRTH_INIT_R69, "controller: distinct dates"),
               (OLD_C_BIRTH_RET_R69, NEW_C_BIRTH_RET_R69, "controller: distinct dates (append)"),
               (OLD_C_BIRTH_R69, NEW_C_BIRTH_R69, "controller: one date, 1982+"),
               (OLD_C_NOTE_R69, NEW_C_NOTE_R69, "controller: filter note"))
README_NOTE_R69 = ('\n\nРЕВИЗИЯ 69 (fix_package_1591.py)\nБыстрее поток строк. Вкладка запоминает ссылку своего заказа (23 часа): новая вкладка\n'
                   'открывает её сразу, без корзины и тарифа, и идёт в «выбрать способ регистрации» → «с сим билайна».\n'
                   'Ссылка выбрасывается, когда клиент подтвердил вход (заказ занят), когда форма по ней не открылась,\n'
                   'после 3 открытий подряд без подтверждения и при смене тарифа. Серая «Продолжить» — следующая строка\n'
                   'в той же форме; новая вкладка только после 3 серых подряд. «С корпоративным номером не получится» —\n'
                   'строка пропускается сразу. «Получить новый запрос» — тоже кнопка повторной отправки. «⚙️ Настройки →\n'
                   '📶 Мобильный прокси» (по умолчанию выключен): браузер через прокси, смена IP по ссылке при «что-то пошло\n'
                   'не так». Загрузка базы «номер|паспорт|даты»: ровно одна дата рождения, 1982 и позже. Маркер:\n'
                   'ORDER_REUSE_1591R69.\n')

# Revision 70: the signature that the site saw as empty. checksignature answered 200 with
# {"isSucceeded": false, "square11": false, "square12": false, "square21": false, "square22": false}: the site checks the
# picture by quarters and found no line in any. The canvas there is «Место для подписи» (SignField-SignCanvas, 436×392,
# 100 % wide, so taller than before): one stroke by fixed fractions of its box could fall outside the window or under
# another element. And that answer counted as «принято» (a 200), so the runtime waited 60 s between clicks, recorded ❔
# after 3 and replaced the tab.
# - SIGN_QUADRANTS_1591R70: the signature canvas is found by its own marks; every quarter gets its own dense stroke
#   (a zigzag along the rows and one along the columns: one thin line covered 1–2 % of a quarter of the bigger canvas),
#   drawn by TOUCH (the field takes finger strokes only: a mouse stroke leaves it empty — that was the bug), through
#   points inside the window that hit the canvas; the canvas pixels are read per quarter, and a quarter without a line is
#   drawn by events sent to the canvas itself. A checksignature answer with isSucceeded false is not «принято»: a
#   redraw and a click at once (2 s), every time; after 4 attempts DeepSeek is asked too, the redraws go on.
# - The tab is never closed for the signature: after 3 clicks with an unchanged page, and after the button vanished
#   with no sign of a signed contract, DeepSeek is asked (again every 3 minutes) instead of ❔ and a new tab.
SIGN_QUADRANTS_MARKER = "SIGN_QUADRANTS_1591R70"
OLD_SIGNQ_MARK_R70 = NEW_ORDER_MARK_R69.splitlines(keepends=True)[-1]
NEW_SIGNQ_MARK_R70 = (OLD_SIGNQ_MARK_R70
                      + '# SIGN_QUADRANTS_1591R70: the signature is drawn per quarter and checked; an empty one is redrawn, the tab is kept.\n')
OLD_SIGNQ_HEAD_R70 = '# REENTER_ROW_1591R67\nREENTER_ROW_MAX_1591R67 = 2\n'
NEW_SIGNQ_HEAD_R70 = r'''# SIGN_QUADRANTS_1591R70
_SIGN_CANVAS_SELECTORS_1591R70 = ('[data-t-id="SignField-SignCanvas"]', 'canvas[aria-label*="подпис" i]',
                                  '[data-testid*="sign" i] canvas', '[class*="sign" i] canvas',
                                  '[class*="signature" i] canvas', "canvas")
SIGN_INK_MIN_1591R70 = 40               # new line pixels a quarter needs
SIGN_EMPTY_RETRY_SECONDS_1591R70 = 2    # redraw at once after the site saw an empty signature
SIGN_EMPTY_AI_AFTER_1591R70 = 4         # DeepSeek is asked too after this many attempts; the redraws go on
_SIGN_REFUSED_RE_1591R70 = re.compile(r'"isSucceeded"\s*:\s*false', re.I)
_QUARTER_NAMES_1591R70 = ("левая верхняя", "правая верхняя", "левая нижняя", "правая нижняя")
_CANVAS_INK_JS_1591R70 = r"""(c) => {
  try {
    const ctx = c.getContext('2d'), w = c.width, h = c.height;
    if (!ctx || !w || !h) return null;
    const d = ctx.getImageData(0, 0, w, h).data;
    const bg = [d[4 * (w + 1)], d[4 * (w + 1) + 1], d[4 * (w + 1) + 2], d[4 * (w + 1) + 3]];
    const counts = [0, 0, 0, 0];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = 4 * (y * w + x);
      if (Math.abs(d[i] - bg[0]) + Math.abs(d[i + 1] - bg[1]) + Math.abs(d[i + 2] - bg[2]) + Math.abs(d[i + 3] - bg[3]) > 60)
        counts[(y < h / 2 ? 0 : 2) + (x < w / 2 ? 0 : 1)]++;
    }
    return counts;
  } catch (e) { return null; }
}"""
_QUARTER_SCROLL_JS_1591R70 = r"""(c, a) => {
  const r = c.getBoundingClientRect();
  const cx = r.left + r.width * (a[0] * 0.5 + 0.25), cy = r.top + r.height * (a[1] * 0.5 + 0.25);
  window.scrollBy(cx < 20 || cx > innerWidth - 20 ? cx - innerWidth / 2 : 0, cy - innerHeight / 2);  // the quarter mid-window
}"""
_QUARTER_POINTS_JS_1591R70 = r"""(c, a) => {
  const [qx, qy, j] = a, r = c.getBoundingClientRect(), out = [];
  const rows = [0.22, 0.42, 0.62, 0.8], cols = [0.15, 0.38, 0.62, 0.85];
  const clamp = (v) => Math.min(0.92, Math.max(0.08, v + j));
  const add = (fx, fy) => {
    const x = r.left + r.width * (qx * 0.5 + 0.5 * clamp(fx)), y = r.top + r.height * (qy * 0.5 + 0.5 * clamp(fy));
    if (x < 1 || y < 1 || x > innerWidth - 2 || y > innerHeight - 2) return;
    const hit = document.elementFromPoint(x, y);
    if (hit === c || c.contains(hit)) out.push([x, y]);
  };
  // a zigzag along the rows, then one along the columns: enough line for the site's check of each quarter
  rows.forEach((fy, i) => { for (const fx of (i % 2 ? cols.slice().reverse() : cols)) add(fx, fy); });
  cols.slice().reverse().forEach((fx, i) => { for (const fy of (i % 2 ? rows : rows.slice().reverse())) add(fx, fy); });
  return out;
}"""
_QUARTER_DISPATCH_JS_1591R70 = r"""(c, a) => {
  const [qx, qy] = a, r = c.getBoundingClientRect();
  const pts = [[0.15, 0.22], [0.85, 0.22], [0.15, 0.42], [0.85, 0.42], [0.15, 0.62], [0.85, 0.62], [0.15, 0.82],
               [0.85, 0.82], [0.85, 0.15], [0.62, 0.85], [0.38, 0.15], [0.15, 0.85]];
  const at = (p) => ({clientX: r.left + r.width * (qx * 0.5 + 0.5 * p[0]), clientY: r.top + r.height * (qy * 0.5 + 0.5 * p[1])});
  const fire = (type, p, buttons) => {
    const o = Object.assign({bubbles: true, cancelable: true, composed: true, view: window, button: 0, buttons,
                             pointerId: 1, pointerType: 'mouse', isPrimary: true, pressure: buttons ? 0.5 : 0}, at(p));
    c.dispatchEvent(type.startsWith('pointer') && window.PointerEvent ? new PointerEvent(type, o) : new MouseEvent(type, o));
  };
  const touch = (type, p) => {
    try {
      const t = new Touch(Object.assign({identifier: 1, target: c, radiusX: 1, radiusY: 1, force: 0.5}, at(p)));
      const live = type === 'touchend' ? [] : [t];
      c.dispatchEvent(new TouchEvent(type, {bubbles: true, cancelable: true, composed: true, touches: live,
                                            targetTouches: live, changedTouches: [t]}));
    } catch (e) {}
  };
  touch('touchstart', pts[0]); fire('pointerdown', pts[0], 1); fire('mousedown', pts[0], 1);
  for (let i = 1; i < pts.length; i++) for (let k = 1; k <= 6; k++) {
    const p = [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k / 6, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k / 6];
    touch('touchmove', p); fire('pointermove', p, 1); fire('mousemove', p, 1);
  }
  const end = pts[pts.length - 1];
  touch('touchend', end); fire('pointerup', end, 0); fire('mouseup', end, 0);
  return true;
}"""


def _sign_canvas_1591r70(page):
    for selector in _SIGN_CANVAS_SELECTORS_1591R70:
        loc = page.locator(selector)
        try:
            count = loc.count()
        except Exception:
            continue
        for i in range(count):
            candidate = loc.nth(i)
            try:
                box = candidate.bounding_box()
                if candidate.is_visible() and box and box["width"] >= 200 and box["height"] >= 100:
                    return candidate
            except Exception:
                continue
    return None


def _canvas_ink_1591r70(canvas):
    try:
        counts = canvas.evaluate(_CANVAS_INK_JS_1591R70)
    except Exception:
        return None
    return [int(x) for x in counts] if isinstance(counts, list) and len(counts) == 4 else None


def _ink_text_1591r70(ink):
    if not ink:
        return "холст не читается"
    return " · ".join(f"{name} {int(n)}" for name, n in zip(_QUARTER_NAMES_1591R70, ink))


def _touch_stroke_1591r70(page, points):
    """One finger stroke through the points: real touch input of the browser (the site's signature field takes
    touches only; mouse strokes leave it empty)."""
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": points[0][0], "y": points[0][1]}]})
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            for k in range(1, 7):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [
                    {"x": x0 + (x1 - x0) * k / 6, "y": y0 + (y1 - y0) * k / 6}]})
            page.wait_for_timeout(15)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    finally:
        try:
            cdp.detach()
        except Exception:
            pass


def _mouse_stroke_1591r70(page, points):
    page.mouse.move(points[0][0], points[0][1])
    page.mouse.down()
    try:
        for x, y in points[1:]:
            page.mouse.move(x, y, steps=6)
            page.wait_for_timeout(20)
    finally:
        page.mouse.up()


def _draw_signature_1591r70(page, diagnostic=None):
    """Every quarter of the signature canvas gets its own stroke through points inside the window that hit the
    canvas (the quarter is scrolled to the middle first): a finger stroke (real touch input: the site's field takes
    touches only), then a mouse stroke where the canvas shows no line yet, then pointer/touch/mouse events sent to
    the canvas itself for a quarter still without enough line. Returns the new line pixels per quarter (square11,
    square12, square21, square22), or None when the canvas cannot be read."""
    canvas = _sign_canvas_1591r70(page)
    if canvas is None:
        raise RuntimeError("Поле графической подписи не найдено.")
    try:
        canvas.evaluate("c => c.scrollIntoView({block: 'center', inline: 'center'})")
    except Exception:
        canvas.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    before = _canvas_ink_1591r70(canvas)
    jitter = (secrets.randbelow(13) - 6) / 100  # each attempt draws new pixels, not the same path again
    how = {}

    def strokes(stroke, quarters, label):
        for quarter in quarters:
            qx, qy = quarter % 2, quarter // 2
            try:
                canvas.evaluate(_QUARTER_SCROLL_JS_1591R70, [qx, qy])
                page.wait_for_timeout(150)
                points = canvas.evaluate(_QUARTER_POINTS_JS_1591R70, [qx, qy, jitter]) or []
            except Exception:
                points = []
            if len(points) < 3:
                how.setdefault(quarter, "закрыта")
                continue
            try:
                stroke(page, points)
                how[quarter] = label
            except Exception as exc:
                how.setdefault(quarter, f"{label}: {type(exc).__name__}")

    def lacking():
        now_ink = _canvas_ink_1591r70(canvas)
        got = [a - b for a, b in zip(now_ink, before)] if before and now_ink else None
        return got, ([q for q in range(4) if got[q] < SIGN_INK_MIN_1591R70] if got else list(range(4)))

    strokes(_touch_stroke_1591r70, range(4), "касание")
    ink, empty = lacking()
    if empty:
        strokes(_mouse_stroke_1591r70, empty, "мышь")
    ink, _ = lacking()
    # a quarter with no line, or with less than half of the best one, is drawn again by events sent to the canvas
    missing = ([q for q in range(4) if ink[q] < max(SIGN_INK_MIN_1591R70, max(ink) // 2)] if ink
               else [q for q in range(4) if how.get(q) not in ("касание", "мышь")])
    for quarter in missing:
        try:
            canvas.evaluate(_QUARTER_DISPATCH_JS_1591R70, [quarter % 2, quarter // 2])
            how[quarter] = "напрямую"
        except Exception:
            pass
    if missing:
        page.wait_for_timeout(200)
        final = _canvas_ink_1591r70(canvas)
        ink = [a - b for a, b in zip(final, before)] if before and final else ink
    try:
        canvas.evaluate("c => c.scrollIntoView({block: 'center'})")
    except Exception:
        pass
    if diagnostic is not None:
        try:
            diagnostic.write("signature_quarters_1591r70", ink=ink, how={str(k): v for k, v in how.items()},
                             box=canvas.bounding_box(), jitter=jitter)
        except Exception:
            pass
    print(f"Подпись нарисована по четвертям: {_ink_text_1591r70(ink)}"
          + (f"; дорисовано напрямую: {', '.join(_QUARTER_NAMES_1591R70[q] for q in missing)}" if missing else ""), flush=True)
    if ink and any(n < SIGN_INK_MIN_1591R70 for n in ink):
        print("⚠️ На холсте нет линии в части четвертей — сайт может не принять подпись.", flush=True)
    return ink


def _sign_trace_refused_1591r70(trace):
    """True as soon as the signing request of this click was answered with isSucceeded false: the trace stops
    waiting there, so the redraw follows at once instead of after the SIGN_TRACE_SECONDS window."""
    for resp, item in (trace or {}).get("_pending") or []:
        if not SIGN_OK_RE_1591R37.search(str(item.get("url") or "")):
            continue
        if "body" not in item:
            try:
                item["body"] = re.sub(r"\s+", " ", str(resp.text() or ""))[:1500]
            except Exception:
                continue
        if _SIGN_REFUSED_RE_1591R70.search(str(item.get("body") or "")):
            return True
    return False


def _sign_empty_1591r70(worker):
    """«пустые четверти 11, 21» when the last click got checksignature isSucceeded false, else ""."""
    trace = (worker or {}).get("sign_trace") or {}
    for response in trace.get("responses") or []:
        body = str(response.get("body") or "")
        if SIGN_OK_RE_1591R37.search(str(response.get("url") or "")) and _SIGN_REFUSED_RE_1591R70.search(body):
            empty = [k for k, v in re.findall(r'"square(\d\d)"\s*:\s*(true|false)', body) if v == "false"]
            return ("пустые четверти " + ", ".join(empty)) if empty else "подпись не принята"
    return ""


def _sign_empty_hold_1591r70(worker, state, now):
    """None when the last click was not answered with an empty signature. Otherwise the tab is kept and the
    signature is redrawn and clicked again at once (False = sign now; True only for the SIGN_EMPTY_RETRY_SECONDS
    the site's answer settles); after SIGN_EMPTY_AI_AFTER attempts DeepSeek is asked once, the redraws go on."""
    squares = _sign_empty_1591r70(worker)
    if not squares:
        return None
    tab_id = worker.get("id")
    if state.get("empty_seen") != state["n"]:
        state["empty_seen"] = state["n"]
        capture_blackbox(worker, "signature_empty")
        print(f"[Вкладка {tab_id}] Сайт не увидел подпись ({squares}) — нарисую заново; вкладку не закрываю.", flush=True)
    if state["n"] >= SIGN_EMPTY_AI_AFTER_1591R70 and not state.get("empty_ai"):
        state["empty_ai"] = True
        queue_success_assist(
            worker,
            f"сайт не видит подпись: checksignature isSucceeded=false ({squares}) после {state['n']} попыток бота. "
            "Вкладку не закрываю: проверь холст «Место для подписи» и помоги подписать договор. Поле принимает только "
            "касания: рисуй через TouchEvent (touchstart/touchmove/touchend) по всем четырём четвертям.",
            force=True,
        )
    wait = SIGN_EMPTY_RETRY_SECONDS_1591R70
    if now - state["at"] >= wait:
        state.update(n=state["n"] + 1, at=now)
        return False
    worker["phase"] = "SUCCESS_ASSIST"
    set_tab_status(worker, "✍️", f"Сайт не увидел подпись ({squares}); попытка {state['n']}, следующая через "
                                 f"{max(1, int(wait - (now - state['at'])))} с. Вкладку не закрываю.")
    return True


''' + OLD_SIGNQ_HEAD_R70
OLD_SIGNQ_FILL_R70 = 'def fill_test_signature(page, diagnostic=None):\n    """Fill the visible signature pad with a test scribble crossing all four quadrants."""\n    selectors = [\n        "canvas",\n        \'[data-testid*="sign" i] canvas\',\n        \'[class*="sign" i] canvas\',\n        \'[class*="signature" i] canvas\',\n    ]\n    canvas = None\n    for selector in selectors:\n        loc = page.locator(selector)\n        for i in range(loc.count()):\n            candidate = loc.nth(i)\n            try:\n                box = candidate.bounding_box()\n                if candidate.is_visible() and box and box["width"] >= 250 and box["height"] >= 120:\n                    canvas = candidate\n                    break\n            except Exception:\n                pass\n        if canvas is not None:\n            break\n\n    if canvas is None:\n        raise RuntimeError("Поле графической подписи не найдено.")\n\n    canvas.scroll_into_view_if_needed()\n    box = canvas.bounding_box()\n    if not box:\n        raise RuntimeError("Не удалось получить координаты поля подписи.")\n\n    x, y, w, h = box["x"], box["y"], box["width"], box["height"]\n\n    # One continuous stroke deliberately visits every quadrant while staying\n    # comfortably inside the pad borders.\n    points = [\n        (0.12, 0.28), (0.28, 0.18), (0.43, 0.36),   # top-left\n        (0.58, 0.20), (0.82, 0.32),                 # top-right\n        (0.68, 0.58), (0.86, 0.76),                 # bottom-right\n        (0.55, 0.68), (0.40, 0.82), (0.18, 0.70),   # bottom-left\n        (0.34, 0.54), (0.62, 0.46), (0.78, 0.62),\n        (0.48, 0.74), (0.24, 0.48),\n    ]\n\n    page.mouse.move(x + points[0][0]*w, y + points[0][1]*h)\n    page.mouse.down()\n    try:\n        for px, py in points[1:]:\n            page.mouse.move(x + px*w, y + py*h, steps=5)\n            page.wait_for_timeout(35)\n    finally:\n        page.mouse.up()\n\n    page.wait_for_timeout(500)\n    if diagnostic is not None:\n        try:\n            diagnostic.write("test_signature_drawn", width=w, height=h)\n        except Exception:\n            pass\n    print("Тестовая подпись нарисована через все 4 квадранта.", flush=True)\n    return True\n\n\n\n'
NEW_SIGNQ_FILL_R70 = ('def fill_test_signature(page, diagnostic=None):\n'
                      '    """Fill the visible signature pad: a stroke in every quarter, checked on the canvas (SIGN_QUADRANTS_1591R70)."""\n'
                      '    _draw_signature_1591r70(page, diagnostic)\n'
                      '    return True\n\n\n\n')
OLD_SIGNQ_THROUGH_R70 = ('        if SIGN_OK_RE_1591R37.search(url) and 200 <= status < 400:\n'
                         '            accepted = True\n')
NEW_SIGNQ_THROUGH_R70 = ('        if SIGN_OK_RE_1591R37.search(url) and 200 <= status < 400:\n'
                         '            if _SIGN_REFUSED_RE_1591R70.search(str(response.get("body") or "")):  # SIGN_QUADRANTS_1591R70\n'
                         '                return False  # «isSucceeded: false»: the site saw no signature\n'
                         '            accepted = True\n')
OLD_SIGNQ_HOLD_R70 = ('    if not state["n"]:\n'
                      '        state.update(n=1, at=now)\n'
                      '        return False\n')
NEW_SIGNQ_HOLD_R70 = (OLD_SIGNQ_HOLD_R70
                      + '    empty_hold = _sign_empty_hold_1591r70(worker, state, now)  # SIGN_QUADRANTS_1591R70: an empty signature\n'
                      '    if empty_hold is not None:\n'
                      '        return empty_hold\n')
OLD_SIGNQ_STUCK_R70 = '''    if state["n"] >= SIGN_CLICKS_MAX_1591R67 and now - state["at"] >= UNVERIFIED_HOLD_SECONDS:
        _finish_unverified_1591r24(
            base_dir, worker,
            f"после {state['n']} нажатий «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не изменилась",
        )
        return True
'''
NEW_SIGNQ_STUCK_R70 = '''    if state["n"] >= SIGN_CLICKS_MAX_1591R67 and now - state["at"] >= UNVERIFIED_HOLD_SECONDS:
        # SIGN_QUADRANTS_1591R70: the tab is kept; DeepSeek is asked, again every UNVERIFIED_HOLD_SECONDS
        if now - float(state.get("stuck_ai_at") or 0) >= UNVERIFIED_HOLD_SECONDS:
            state["stuck_ai_at"] = now
            queue_success_assist(
                worker,
                f"после {state['n']} нажатий «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не изменилась. "
                "Вкладку не закрываю: найди, что мешает, и доведи подпись.",
                force=True,
            )
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(worker, "🧠", f"Подпись нажата {state['n']} раза, страница не меняется — DeepSeek разбирается; "
                                     "вкладку не закрываю.")
        return True
'''
OLD_SIGNQ_SETTLE_R70 = '''    _finish_unverified_1591r24(
        base_dir, worker,
        f"после «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не показала признаков подписания (URL: {url or '—'})",
    )
    return False
'''
NEW_SIGNQ_SETTLE_R70 = '''    # SIGN_QUADRANTS_1591R70: no ❔ and no new tab; DeepSeek is asked again every UNVERIFIED_HOLD_SECONDS
    worker["phase"] = "SUCCESS_ASSIST"
    if now - float(worker.get("unverified_ai_at_1591r70") or since) >= UNVERIFIED_HOLD_SECONDS:
        worker["unverified_ai_at_1591r70"] = now
        queue_success_assist(
            worker,
            f"после «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не показала признаков подписания "
            f"(URL: {url or '—'}). Вкладку не закрываю: проверь, подписан ли договор, и доведи его.",
            force=True,
        )
    return False
'''
OLD_SIGNQ_UNSEEN_R70 = '''            else:
                queue_success_assist(
                    worker,
                    "подпись нажата, но запроса подписи в сети не видно; проверь ошибки/обязательные поля",
                    force=True,
                )
'''
NEW_SIGNQ_UNSEEN_R70 = '''            elif _sign_empty_1591r70(worker):  # SIGN_QUADRANTS_1591R70: redrawn by _sign_hold_1591r67
                print(
                    f"[Вкладка {worker['id']}] Сайт ответил, что подпись пустая ({_sign_empty_1591r70(worker)}); "
                    "перерисовываю сразу.",
                    flush=True,
                )
            else:
                queue_success_assist(
                    worker,
                    "подпись нажата, но запроса подписи в сети не видно; проверь ошибки/обязательные поля",
                    force=True,
                )
'''
OLD_SIGNQ_TRACE_R70 = ('    deadline = monotonic() + SIGN_TRACE_SECONDS\n'
                       '    while monotonic() < deadline:\n'
                       '        try:\n'
                       '            page.wait_for_timeout(250)\n'
                       '        except Exception:\n'
                       '            break\n')
NEW_SIGNQ_TRACE_R70 = (OLD_SIGNQ_TRACE_R70
                       + '        if _sign_trace_refused_1591r70(trace):  # SIGN_QUADRANTS_1591R70: «empty» already said, redraw now\n'
                       '            break\n')
SIGNQ_EDITS_R70 = ((OLD_SIGNQ_MARK_R70, NEW_SIGNQ_MARK_R70, "signature quarters: marker"),
                   (OLD_SIGNQ_TRACE_R70, NEW_SIGNQ_TRACE_R70, "signature quarters: the trace ends at an empty answer"),
                   (OLD_SIGNQ_HEAD_R70, NEW_SIGNQ_HEAD_R70, "signature quarters: helpers"),
                   (OLD_SIGNQ_FILL_R70, NEW_SIGNQ_FILL_R70, "signature quarters: fill_test_signature"),
                   (OLD_SIGNQ_THROUGH_R70, NEW_SIGNQ_THROUGH_R70, "signature quarters: isSucceeded false is no success"),
                   (OLD_SIGNQ_HOLD_R70, NEW_SIGNQ_HOLD_R70, "signature quarters: redraw an empty signature"),
                   (OLD_SIGNQ_STUCK_R70, NEW_SIGNQ_STUCK_R70, "signature quarters: no ❔ after 3 clicks"),
                   (OLD_SIGNQ_SETTLE_R70, NEW_SIGNQ_SETTLE_R70, "signature quarters: no ❔ after the button vanished"),
                   (OLD_SIGNQ_UNSEEN_R70, NEW_SIGNQ_UNSEEN_R70, "signature quarters: an empty answer is not «unseen»"))
README_NOTE_R70 = ('\n\nРЕВИЗИЯ 70 (fix_package_1591.py)\nПодпись. Сайт проверяет картинку подписи по четвертям (checksignature: isSucceeded, square11…22)\n'
                   'и видел её пустой, а бот считал ответ 200 принятой подписью, ждал минуту, после 3 нажатий ставил «❔» и\n'
                   'менял вкладку. Теперь холст «Место для подписи» ищется по своим меткам, каждая четверть рисуется своей\n'
                   'линией КАСАНИЕМ (поле подписи принимает только касания, мышь оставляла его пустым) через точки на экране,\n'
                   'которые попадают в холст; пиксели холста проверяются по четвертям, пустая\n'
                   'дорисовывается событиями прямо в холст. Ответ «isSucceeded: false» — сразу перерисовка и нажатие, каждый\n'
                   'раз; после 4 попыток подключается DeepSeek, перерисовка идёт дальше. Вкладка из-за подписи не\n'
                   'закрывается: вместо «❔» — DeepSeek.\n'
                   'Маркер: SIGN_QUADRANTS_1591R70.\n')

# Revision 71: DeepSeek as an agent with a memory, and a row that resumes where it stopped.
# - AGENT_MEMORY_1591R71: the dialogue was never remembered (_chat_memory_append was defined and called nowhere), so
#   every message started from nothing. Now each answered message of the owner (not the automatic jobs) is written
#   with the reply to ai_chat_memory.jsonl, and the last 12 turns of the last 12 hours go to the agent as real
#   messages (the quick-chat route reads the same file). A short «да / давай / сделай / повтори» after an answer is a
#   follow-up: it goes to the tool route with live actions allowed. Any message of 15+ characters goes to the agent
#   with tools, only short chatter keeps the single quick answer. DeepSeek can draw the signature: the tool
#   browser_draw_signature draws by touch (the field takes touches only) and returns the ink per quarter.
# - CONFIRM_RESUME_1591R71: the attempt (1..6) of a row in the confirmation is kept per number in confirm_progress/.
#   After a restart of the bot, a replaced page or any error the row starts at the attempt where it stopped, not at
#   1/6. The record is dropped when the row is finished or the client confirmed.
AGENT_MEMORY_MARKER = "AGENT_MEMORY_1591R71"
OLD_MEM_MARK_R71 = NEW_SIGNQ_MARK_R70.splitlines(keepends=True)[-1]
NEW_MEM_MARK_R71 = (OLD_MEM_MARK_R71
                    + '# AGENT_MEMORY_1591R71: DeepSeek remembers the dialogue, draws the signature by touch; a row resumes its attempt.\n')
OLD_MEM_HEAD_R71 = '# REENTER_ROW_1591R67\nREENTER_ROW_MAX_1591R67 = 2\n'
NEW_MEM_HEAD_R71 = r'''# AGENT_MEMORY_1591R71
CHAT_MEMORY_TURNS_1591R71 = 12              # messages (6 exchanges) given to the agent
CHAT_MEMORY_MAX_AGE_1591R71 = 12 * 3600     # older talk is not "the previous dialogue" any more
CHAT_MEMORY_KEEP_LINES_1591R71 = 200
CHAT_MEMORY_TEXT_1591R71 = 2500
_FOLLOWUP_WORDS_1591R71 = ("да", "давай", "делай", "сделай", "ок", "окей", "хорошо", "продолжай", "дальше",
                           "ещё раз", "еще раз", "повтори", "попробуй", "пробуй", "согласен", "угу")
_REPLY_HEADS_1591R71 = ("🤖 DeepSeek Operator\n\n", "🤖 DeepSeek Operator\n", "🤖 ")


def _chat_memory_entries_1591r71():
    try:
        lines = AI_CHAT_MEMORY_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    now, out = time.time(), []
    for line in lines[-80:]:
        try:
            rec = json.loads(line)
            stamp = time.mktime(time.strptime(str(rec.get("time")), "%Y-%m-%d %H:%M:%S"))
        except Exception:
            continue
        text = str(rec.get("text") or "").strip()
        if rec.get("role") in ("user", "assistant") and text and 0 <= now - stamp <= CHAT_MEMORY_MAX_AGE_1591R71:
            out.append({"role": rec["role"], "content": text[:CHAT_MEMORY_TEXT_1591R71]})
    return out


def _chat_history_messages_1591r71(limit=None):
    """The last turns of the dialogue as chat messages: they start with the owner's message, end with the
    answer to it, and the same roles are merged (the API wants them alternating)."""
    merged = []
    for item in _chat_memory_entries_1591r71():
        if merged and merged[-1]["role"] == item["role"]:
            merged[-1]["content"] = (merged[-1]["content"] + "\n" + item["content"])[:CHAT_MEMORY_TEXT_1591R71]
        else:
            merged.append(dict(item))
    while merged and merged[0]["role"] != "user":
        merged.pop(0)
    while merged and merged[-1]["role"] != "assistant":
        merged.pop()
    return merged[-(limit or CHAT_MEMORY_TURNS_1591R71):]


def _chat_memory_pair_1591r71(user_text, reply):
    """Remember one answered exchange of the owner. The automatic jobs, the silent «-» and the failures are not
    dialogue and stay out; the file is cut to its last lines."""
    user_text, reply = str(user_text or "").strip(), str(reply or "").strip()
    if not user_text or not reply or user_text.upper().startswith("[AUTO_") or reply.startswith("⚠️"):
        return False
    for head in _REPLY_HEADS_1591R71:
        if reply.startswith(head):
            reply = reply[len(head):].strip()
            break
    if not reply or reply in {"-", "—", "–"}:
        return False
    try:
        _chat_memory_append("user", user_text)
        _chat_memory_append("assistant", reply)
        lines = AI_CHAT_MEMORY_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > CHAT_MEMORY_KEEP_LINES_1591R71 * 2:
            tmp = AI_CHAT_MEMORY_FILE.with_suffix(".tmp")
            tmp.write_text("\n".join(lines[-CHAT_MEMORY_KEEP_LINES_1591R71:]) + "\n", encoding="utf-8")
            tmp.replace(AI_CHAT_MEMORY_FILE)
    except Exception:
        return False
    return True


def _followup_1591r71(text):
    """A short agreement or «again» right after an answer: «да», «давай», «сделай», «повтори»…"""
    low = re.sub(r"[\s.,!?…]+$", "", str(text or "").lower().strip())
    if not low or len(low) > 32 or low.startswith(("/", "[auto_")):
        return False
    first = re.split(r"[\s,.!]+", low, maxsplit=1)[0]
    if not (first in _FOLLOWUP_WORDS_1591R71 or low.startswith(("ещё раз", "еще раз"))):
        return False
    return bool(_chat_history_messages_1591r71())


def _agent_message_1591r71(text):
    """A real message (15+ characters, not an automatic job) goes to the agent with tools; only short chatter
    keeps the single quick answer."""
    low = str(text or "").strip()
    return len(low) >= 15 and not low.lower().startswith("[auto_")


# CONFIRM_RESUME_1591R71
CONFIRM_PROGRESS_DIR_1591R71 = "confirm_progress"
CONFIRM_PROGRESS_MAX_AGE_1591R71 = 12 * 3600


def _confirm_progress_path_1591r71(base_dir, row):
    number = _row_number_value(row) if row is not None else ""
    if not number:
        return None
    return Path(base_dir or Path(__file__).resolve().parent) / CONFIRM_PROGRESS_DIR_1591R71 / f"{number}.json"


def _confirm_progress_save_1591r71(base_dir, row, attempt):
    path = _confirm_progress_path_1591r71(base_dir, row)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"attempt": int(attempt), "time": time.time()}), "utf-8")
        tmp.replace(path)
    except Exception:
        return False
    return True


def _confirm_progress_load_1591r71(base_dir, row):
    """The attempt (1..6) the row stopped at, 1 when there is nothing fresh."""
    path = _confirm_progress_path_1591r71(base_dir, row)
    try:
        rec = json.loads(path.read_text("utf-8")) if path is not None else {}
        attempt = int(rec.get("attempt") or 1)
        if time.time() - float(rec.get("time") or 0) > CONFIRM_PROGRESS_MAX_AGE_1591R71:
            return 1
    except Exception:
        return 1
    return attempt if 1 <= attempt <= 6 else 1


def _confirm_progress_clear_1591r71(base_dir, row):
    path = _confirm_progress_path_1591r71(base_dir, row)
    try:
        if path is not None:
            path.unlink()
    except Exception:
        pass


def _confirm_progress_tick_1591r71(base_dir, worker):
    """Keep the row's attempt on disk while it waits for the client; drop it once the client confirmed."""
    phase, row = worker.get("phase"), worker.get("row")
    if phase in ("CONFIRM", "RESEND"):
        attempt = int(worker.get("confirm_attempt") or 0)
        key = (worker.get("generation"), attempt)
        if attempt and worker.get("conf_saved_1591r71") != key:
            worker["conf_saved_1591r71"] = key
            _confirm_progress_save_1591r71(base_dir, row, attempt)
    elif phase in _ORDER_TAKEN_PHASES_1591R69 and worker.get("conf_saved_1591r71"):
        worker["conf_saved_1591r71"] = None
        _confirm_progress_clear_1591r71(base_dir, row)


''' + OLD_MEM_HEAD_R71
OLD_MEM_TICK_R71 = '    phase, gen = worker.get("phase"), worker.get("generation")\n    if phase in _ORDER_TAKEN_PHASES_1591R69 and worker.get("order_taken_1591r69") != gen:\n'
NEW_MEM_TICK_R71 = ('    phase, gen = worker.get("phase"), worker.get("generation")\n'
                    '    (globals().get("_confirm_progress_tick_1591r71") or (lambda *a: None))(base_dir, worker)  # CONFIRM_RESUME_1591R71\n'
                    '    if phase in _ORDER_TAKEN_PHASES_1591R69 and worker.get("order_taken_1591r69") != gen:\n')
OLD_MEM_BEGIN_R71 = ('    worker["confirm_attempt"] = 1\n'
                     '    entered_at = worker.get("auth_entered_at")\n'
                     '    worker["confirm_deadline"] = (entered_at if entered_at is not None else now) + 65\n'
                     '    external_heartbeat(worker, "confirm_wait")\n'
                     '    set_tab_status(worker, "🟡", "Ожидаю подтверждение: попытка 1/6")\n'
                     '    print(\n'
                     '        f"[Вкладка {worker[\'id\']}] Экран подтверждения открыт. "\n'
                     '        "Запущен собственный таймер 65 секунд (попытка 1/6).",\n'
                     '        flush=True,\n'
                     '    )\n')
NEW_MEM_BEGIN_R71 = ('    # CONFIRM_RESUME_1591R71: after a restart / a replaced page the row goes on from the attempt it stopped at\n'
                     '    attempt = (globals().get("_confirm_progress_load_1591r71") or (lambda *a: 1))(worker.get("base_dir"), worker.get("row"))\n'
                     '    worker["confirm_attempt"] = attempt\n'
                     '    entered_at = worker.get("auth_entered_at")\n'
                     '    worker["confirm_deadline"] = (entered_at if entered_at is not None else now) + 65\n'
                     '    external_heartbeat(worker, "confirm_wait")\n'
                     '    set_tab_status(worker, "🟡", f"Ожидаю подтверждение: попытка {attempt}/6")\n'
                     '    print(\n'
                     '        f"[Вкладка {worker[\'id\']}] Экран подтверждения открыт. "\n'
                     '        f"Запущен собственный таймер 65 секунд (попытка {attempt}/6"\n'
                     '        + (", продолжаю с той, на которой остановился)." if attempt > 1 else ")."),\n'
                     '        flush=True,\n'
                     '    )\n')
OLD_MEM_PROCESSED_R71 = ('    number = _row_number_value(row)\n'
                         '    if not number:\n'
                         '        return\n'
                         '    path = Path(base_dir) / PROGRESS_FILE_NAME\n')
NEW_MEM_PROCESSED_R71 = ('    number = _row_number_value(row)\n'
                         '    if not number:\n'
                         '        return\n'
                         '    (globals().get("_confirm_progress_clear_1591r71") or (lambda *a: None))(base_dir, row)  # CONFIRM_RESUME_1591R71\n'
                         '    path = Path(base_dir) / PROGRESS_FILE_NAME\n')
OLD_MEM_LIVE_R71 = 'def _explicit_live_action_request(text):\n    low = str(text or "").lower().strip()\n    if not low:\n        return False\n'
NEW_MEM_LIVE_R71 = (OLD_MEM_LIVE_R71
                    + '    if (globals().get("_followup_1591r71") or (lambda t: False))(text):  # AGENT_MEMORY_1591R71: «да, сделай» after an answer\n'
                    '        return True\n')
OLD_MEM_NEEDS_R71 = 'def _operator_needs_tools(text):\n    low = str(text or "").lower().strip()\n    if not low:\n        return False\n'
NEW_MEM_NEEDS_R71 = (OLD_MEM_NEEDS_R71
                     + '    if (globals().get("_followup_1591r71") or (lambda t: False))(text) \\\n'
                     '            or (globals().get("_agent_message_1591r71") or (lambda t: False))(text):  # AGENT_MEMORY_1591R71: an agent, not a status button\n'
                     '        return True\n')
OLD_MEM_MESSAGES_R71 = ('    messages = [\n'
                        '        {"role": "system", "content": system_prompt},\n'
                        '        {"role": "user", "content": user_content},\n'
                        '    ]\n'
                        '    round_no = 0\n')
NEW_MEM_MESSAGES_R71 = ('    # AGENT_MEMORY_1591R71: the dialogue so far goes in as real messages, the new one is the last\n'
                        '    history = [] if str(user_text or "").lstrip().upper().startswith("[AUTO_") else \\\n'
                        '        (globals().get("_chat_history_messages_1591r71") or (lambda: []))()\n'
                        '    if history:\n'
                        '        user_content[0]["text"] = str(user_text)\n'
                        '    messages = [\n'
                        '        {"role": "system", "content": system_prompt},\n'
                        '        *history,\n'
                        '        {"role": "user", "content": user_content},\n'
                        '    ]\n'
                        '    round_no = 0\n')
OLD_MEM_SAVE_R71 = '            print(f"[AI {lane.upper()}] update {update_id} завершён.", flush=True)\n'
NEW_MEM_SAVE_R71 = ('            (globals().get("_chat_memory_pair_1591r71") or (lambda *a: None))(latest, response_text)  # AGENT_MEMORY_1591R71: remembered\n'
                    + OLD_MEM_SAVE_R71)
OLD_MEM_TOOL_R71 = ('        {\n'
                    '            "type": "function",\n'
                    '            "function": {\n'
                    '                "name": "browser_evaluate_js",\n')
NEW_MEM_TOOL_R71 = ('        {\n'
                    '            "type": "function",\n'
                    '            "function": {\n'
                    '                "name": "browser_draw_signature",\n'
                    '                "description": "Нарисовать подпись в поле «Место для подписи» живой вкладки настоящим касанием по всем '
                    'четырём четвертям (поле принимает только касания; мышь и JS-события оно не засчитывает) и вернуть, сколько линии '
                    'появилось в каждой четверти. После неё нажми «Подписать договор» и проверь ответ checksignature.",\n'
                    '                "strict": True,\n'
                    '                "parameters": {\n'
                    '                    "type":"object",\n'
                    '                    "properties":{"tab":{"type":"integer","minimum":1,"maximum":TAB_COUNT}},\n'
                    '                    "required":["tab"],"additionalProperties":False\n'
                    '                },\n'
                    '            },\n'
                    '        },\n'
                    + OLD_MEM_TOOL_R71)
OLD_MEM_MUT_R71 = '            "browser_close_tab", "browser_open_page",\n        }\n'
NEW_MEM_MUT_R71 = '            "browser_close_tab", "browser_open_page", "browser_draw_signature",  # AGENT_MEMORY_1591R71\n        }\n'
OLD_MEM_MAP_R71 = '                "browser_close_tab": "CLOSE_TAB",\n            }\n'
NEW_MEM_MAP_R71 = '                "browser_close_tab": "CLOSE_TAB",\n                "browser_draw_signature": "DRAW_SIGNATURE",  # AGENT_MEMORY_1591R71\n            }\n'
OLD_MEM_LIVE_NAMES_R71 = '        "browser_close_tab", "browser_open_page", "request_runtime_action",\n        "run_terminal",\n    }\n'
NEW_MEM_LIVE_NAMES_R71 = '        "browser_close_tab", "browser_open_page", "request_runtime_action",\n        "run_terminal", "browser_draw_signature",  # AGENT_MEMORY_1591R71\n    }\n'
OLD_MEM_HOST_R71 = '                    if kind == "EVALUATE_JS":\n'
NEW_MEM_HOST_R71 = ('                    if kind == "DRAW_SIGNATURE":  # AGENT_MEMORY_1591R71: by touch, per quarter, checked on the canvas\n'
                    '                        ink = _draw_signature_1591r70(page)\n'
                    '                        return {"ok": True, "ink_per_quarter": ink, "quarters": list(_QUARTER_NAMES_1591R70), "url": page.url,\n'
                    '                                "note": "подпись нарисована касанием; теперь нажми «Подписать договор» и проверь checksignature"}\n'
                    + OLD_MEM_HOST_R71)
OLD_MEM_PROMPT_R71 = '  запрашивать restart worker и выполнять terminal-команды.\n'
NEW_MEM_PROMPT_R71 = (OLD_MEM_PROMPT_R71
                      + '- рисовать подпись настоящим касанием (инструмент browser_draw_signature): поле подписи сайта принимает только касания.\n\n'
                      'ТЫ АГЕНТ С ПАМЯТЬЮ (AGENT_MEMORY_1591R71): предыдущие сообщения этого диалога переданы выше — опирайся на них; '
                      '«да», «давай», «сделай» — согласие с тем, что ты сам предложил. Если просят что-то сделать — делай инструментами, '
                      'проверь результат и ответь по факту, а не описанием того, что можно было бы сделать. Отвечай коротко, по-русски.\n')
OLD_MEM_SIGN_R71 = '        "Затем правильно заполни поле подписи, дождись активной кнопки и нажми "\n'
NEW_MEM_SIGN_R71 = ('        "ПОДПИСЬ РИСУЙ ТОЛЬКО инструментом browser_draw_signature: поле «Место для подписи» принимает лишь касания, мышь и JS-события "  # AGENT_MEMORY_1591R71\n'
                    '        "оно не засчитывает (сайт проверяет четыре четверти: checksignature → isSucceeded, square11…square22). "\n'
                    '        "СТРОКУ БРОСАТЬ НЕЛЬЗЯ: клиент уже подтвердил вход. Если подпись не принялась — нарисуй снова, нажми «Подписать договор» "\n'
                    '        "ещё раз и смотри ответ checksignature; «Не подписано» пиши, только если сайт сам вернул заказ в начало. "\n'
                    + OLD_MEM_SIGN_R71)
MEM_EDITS_R71 = ((OLD_MEM_MARK_R71, NEW_MEM_MARK_R71, "agent memory: marker"),
                 (OLD_MEM_HEAD_R71, NEW_MEM_HEAD_R71, "agent memory: helpers"),
                 (OLD_MEM_TICK_R71, NEW_MEM_TICK_R71, "confirm resume: keep the attempt"),
                 (OLD_MEM_BEGIN_R71, NEW_MEM_BEGIN_R71, "confirm resume: start at the saved attempt"),
                 (OLD_MEM_PROCESSED_R71, NEW_MEM_PROCESSED_R71, "confirm resume: drop it when the row is finished"),
                 (OLD_MEM_LIVE_R71, NEW_MEM_LIVE_R71, "agent memory: a follow-up is a live request"),
                 (OLD_MEM_NEEDS_R71, NEW_MEM_NEEDS_R71, "agent memory: a real message goes to the agent"),
                 (OLD_MEM_MESSAGES_R71, NEW_MEM_MESSAGES_R71, "agent memory: the dialogue as messages"),
                 (OLD_MEM_SAVE_R71, NEW_MEM_SAVE_R71, "agent memory: remember the exchange"),
                 (OLD_MEM_TOOL_R71, NEW_MEM_TOOL_R71, "agent memory: tool browser_draw_signature"),
                 (OLD_MEM_MUT_R71, NEW_MEM_MUT_R71, "agent memory: tool is a mutation"),
                 (OLD_MEM_MAP_R71, NEW_MEM_MAP_R71, "agent memory: tool action name"),
                 (OLD_MEM_LIVE_NAMES_R71, NEW_MEM_LIVE_NAMES_R71, "agent memory: tool allowed on live tasks"),
                 (OLD_MEM_HOST_R71, NEW_MEM_HOST_R71, "agent memory: host draws the signature"),
                 (OLD_MEM_PROMPT_R71, NEW_MEM_PROMPT_R71, "agent memory: system prompt"),
                 (OLD_MEM_SIGN_R71, NEW_MEM_SIGN_R71, "agent memory: signing prompt"))
README_NOTE_R71 = ('\n\nРЕВИЗИЯ 71 (fix_package_1591.py)\nDeepSeek как агент с памятью. Раньше разговор не запоминался вообще (функция записи была,\n'
                   'но нигде не вызывалась): каждое сообщение — с нуля. Теперь каждый отвеченный обмен пишется в ai_chat_memory.jsonl,\n'
                   'и последние 12 сообщений за 12 часов передаются агенту настоящими сообщениями. Короткое «да / давай / сделай /\n'
                   'повтори» после ответа — продолжение: идёт в режим с инструментами и живыми действиями. Любое сообщение от 15\n'
                   'символов идёт к агенту с инструментами. Новый инструмент browser_draw_signature рисует подпись касанием (поле\n'
                   'принимает только касания). Попытка из шести хранится по номеру в confirm_progress/: после перезапуска бота,\n'
                   'замены страницы или ошибки строка идёт с той же попытки, а не с 1/6. Маркер: AGENT_MEMORY_1591R71.\n')

# Revision 72: a confirmed row must be signed while the client's confirmation lives (under 3 minutes: row 1243 of
# 11.10 got 412 PERSONAL_TOKEN_ERROR 2 min 50 s after the client confirmed).
# - REGION_CAPTION_1591R72: an empty region field is captioned «укажите область» by the site, not «область»; the r55
#   marker wanted the caption to start with «область», found no field, the runtime waited 45 s and DeepSeek filled it
#   in 2 more minutes. «укажите область» / «укажите регион» is a region caption now, so the runtime fills it at once.
# - FAST_ASSIST_1591R72: a disabled «Подписать договор» calls DeepSeek after 8 s, not after 45 s.
# - REENTER_SIX_1591R72: «введите данные снова — с заказом всё хорошо» (the site says it after «Отправить снова»,
#   159 times in 14 h on one server) re-enters the row up to 6 times, not 2: the attempt number goes on (r71), so a
#   row uses its six attempts instead of being skipped after the second re-entry.
# - The log line «клиент подтвердил вход» is written only when he did (the success guard); an error page after the
#   confirmation screen says so instead.
REGION_CAPTION_MARKER = "REGION_CAPTION_1591R72"
OLD_REG_MARK_R72 = NEW_MEM_MARK_R71.splitlines(keepends=True)[-1]
NEW_REG_MARK_R72 = (OLD_REG_MARK_R72
                    + '# REGION_CAPTION_1591R72: «укажите область» is filled at once; DeepSeek after 8 s; up to 6 re-entries.\n')
OLD_REG_REGEX_R72 = '    if (/^(область|регион)([\\s,/(].*)?$/.test(cap) && !/район/.test(cap)) {\n'
NEW_REG_REGEX_R72 = ('    // REGION_CAPTION_1591R72: the empty field is captioned «укажите область» by the site\n'
                     '    if (/^(укажите\\s+)?(область|регион)([\\s,/(].*)?$/.test(cap) && !/район/.test(cap)) {\n')
OLD_REG_QUIET_R72 = '            if _quiet_wait_1591r57(worker, "quiet_button_1591r57"):  # QUIET_AUTO_1591R57: the site may still be filling the form\n'
NEW_REG_QUIET_R72 = ('            # FAST_ASSIST_1591R72: the client\'s confirmation lives under 3 minutes; DeepSeek after 8 s, not 45 s\n'
                     '            if _quiet_wait_short_1591r72(worker, "quiet_button_1591r57"):\n')
OLD_REG_REENTER_R72 = 'REENTER_ROW_MAX_1591R67 = 2\n'
NEW_REG_REENTER_R72 = 'REENTER_ROW_MAX_1591R67 = 6  # REENTER_SIX_1591R72: a row uses its six attempts (was 2)\n'
OLD_REG_FORGET_R72 = '        _forget_order_1591r69(worker, "клиент подтвердил вход — заказ занят этой строкой")\n'
NEW_REG_FORGET_R72 = ('        _forget_order_1591r69(worker, "клиент подтвердил вход — заказ занят этой строкой" if worker.get("success_guard")\n'
                      '                              else "после экрана подтверждения открылась ошибка — заказ не переиспользую")  # REGION_CAPTION_1591R72\n')
OLD_REG_HEAD_R72 = '# REENTER_ROW_1591R67\nREENTER_ROW_MAX_1591R67 = 2\n'
NEW_REG_HEAD_R72 = r'''# FAST_ASSIST_1591R72
QUIET_WAIT_SHORT_SECONDS_1591R72 = 8


def _quiet_wait_short_1591r72(worker, key):
    """_quiet_wait_1591r57 with QUIET_WAIT_SHORT_SECONDS_1591R72: on the contract page the confirmation is running out."""
    try:
        url = str(worker.get("page").url or "")
    except Exception:
        url = ""
    mark = [str(worker.get("row")), url]
    state = worker.get(key)
    now = monotonic()
    if not state or state.get("mark") != mark:
        state = {"mark": mark, "since": now}
        worker[key] = state
    return now - float(state["since"]) >= QUIET_WAIT_SHORT_SECONDS_1591R72


''' + '# REENTER_ROW_1591R67\n' + NEW_REG_REENTER_R72
REG_EDITS_R72 = ((OLD_REG_MARK_R72, NEW_REG_MARK_R72, "region caption: marker"),
                 (OLD_REG_REGEX_R72, NEW_REG_REGEX_R72, "region caption: «укажите область»"),
                 (OLD_REG_QUIET_R72, NEW_REG_QUIET_R72, "fast assist: 8 s"),
                 (OLD_REG_FORGET_R72, NEW_REG_FORGET_R72, "order forget: the honest reason"),
                 (OLD_REG_HEAD_R72, NEW_REG_HEAD_R72, "fast assist: helper; re-enter: 6 times"))
README_NOTE_R72 = ('\n\nРЕВИЗИЯ 72 (fix_package_1591.py)\nПодтверждение клиента живёт меньше 3 минут: строка 1243 получила 412 PERSONAL_TOKEN_ERROR через\n'
                   '2 мин 50 с. Пустую область сайт подписывает «укажите область», а бот искал поле с подписью «область»,\n'
                   'не находил его, ждал 45 с и звал DeepSeek, который заполнял ещё 2 минуты. Теперь «укажите область» узнаётся,\n'
                   'бот заполняет поле сам сразу; при серой кнопке DeepSeek зовётся через 8 с, а не через 45. «Введите данные\n'
                   'снова» — до 6 повторов строки (было 2), номер попытки продолжается. Надпись «клиент подтвердил вход» —\n'
                   'только когда он подтвердил. Маркер: REGION_CAPTION_1591R72.\n')

# Revision 73: the menu only. «📂 База → 🔁 Сбросить прогресс» (BASE_RESET_1591R73) starts the loaded base from its first
# row again: the processed numbers and the deferred rows go to base_archive/ and are removed, the work is restarted. And
# «⚙️ Настройки → 📤 Выгрузка» (PUSH_COUNT_1591R73): how many eSIM «📤 Выгрузка» gives by default, 6, can be raised.
BASE_RESET_MARKER = "BASE_RESET_1591R73"
OLD_RESET_MARK_R73 = NEW_REG_MARK_R72.splitlines(keepends=True)[-1]
NEW_RESET_MARK_R73 = (OLD_RESET_MARK_R73
                      + '# BASE_RESET_1591R73: the menu resets the base progress; the export count has a default setting.\n')
README_NOTE_R73 = ('\n\nРЕВИЗИЯ 73 (fix_package_1591.py)\nТолько меню. «📂 База → 🔁 Сбросить прогресс»: база идёт с первой строки (список обработанных номеров и\n'
                   'отложенные строки уходят в base_archive и очищаются, бот перезапускается; «Мои eSIM» не трогаются). «⚙️ Настройки →\n'
                   '📤 Выгрузка»: сколько eSIM даёт «📤 Выгрузка» по умолчанию (6, можно поднять до 500). Маркер: BASE_RESET_1591R73.\n')

# Revision 74: the number of push requests a client gets on the confirmation page is a setting. Until now it was a six in
# the code: the first request and five «Отправить снова» at 65 s each. «⚙️ Настройки → 📲 Push» sets it (6 by default,
# up to 30): BEELINE_CONFIRM_ATTEMPTS. The r73 setting «Выгрузка по умолчанию» (how many eSIM an export gives) was a
# misreading of the request and is gone from the menu.
CONFIRM_PUSH_MARKER = "CONFIRM_PUSH_1591R74"
OLD_PUSH_MARK_R74 = NEW_RESET_MARK_R73.splitlines(keepends=True)[-1]
NEW_PUSH_MARK_R74 = (OLD_PUSH_MARK_R74
                     + '# CONFIRM_PUSH_1591R74: push requests on the confirmation page are a setting (BEELINE_CONFIRM_ATTEMPTS, 6 by default).\n')
OLD_PUSH_HEAD_R74 = '# REENTER_ROW_1591R67\nREENTER_ROW_MAX_1591R67 = 6  # REENTER_SIX_1591R72: a row uses its six attempts (was 2)\n'
NEW_PUSH_HEAD_R74 = ('# CONFIRM_PUSH_1591R74\n'
                     'def _confirm_attempts_1591r74():\n'
                     '    """How many push requests a client gets on the confirmation page: BEELINE_CONFIRM_ATTEMPTS, 6 by default, 1..30."""\n'
                     '    try:\n'
                     '        n = int(str(os.environ.get("BEELINE_CONFIRM_ATTEMPTS") or "").strip())\n'
                     '    except ValueError:\n'
                     '        return 6\n'
                     '    return n if 1 <= n <= 30 else 6\n'
                     '\n\n'
                     'CONFIRM_ATTEMPTS_1591R74 = _confirm_attempts_1591r74()\n\n\n'
                     + OLD_PUSH_HEAD_R74)
PUSH_SITES_R74 = (
    ('''    if worker.get("confirm_attempt"): lines.append(f"Подтверждение: {worker['confirm_attempt']}/6")\n''',
     '''    if worker.get("confirm_attempt"): lines.append(f"Подтверждение: {worker['confirm_attempt']}/{CONFIRM_ATTEMPTS_1591R74}")  # CONFIRM_PUSH_1591R74\n''',
     "confirm push: the status line"),
    ('''    set_tab_status(worker, "🟡", f"Ожидаю подтверждение: попытка {attempt}/6")\n''',
     '''    set_tab_status(worker, "🟡", f"Ожидаю подтверждение: попытка {attempt}/{CONFIRM_ATTEMPTS_1591R74}")\n''',
     "confirm push: begin, status"),
    ('''        f"Запущен собственный таймер 65 секунд (попытка {attempt}/6"\n''',
     '''        f"Запущен собственный таймер 65 секунд (попытка {attempt}/{CONFIRM_ATTEMPTS_1591R74}"\n''',
     "confirm push: begin, log"),
    ('''    return attempt if 1 <= attempt <= 6 else 1\n''',
     '''    return attempt if 1 <= attempt <= CONFIRM_ATTEMPTS_1591R74 else 1\n''',
     "confirm push: saved attempt"),
    ('''    if worker["confirm_attempt"] >= 6:\n''',
     '''    if worker["confirm_attempt"] >= CONFIRM_ATTEMPTS_1591R74:  # CONFIRM_PUSH_1591R74\n''',
     "confirm push: the cap"),
    ('''        set_tab_status(worker, "🟠", "6 попыток завершены — беру следующую строку")\n''',
     '''        set_tab_status(worker, "🟠", f"{CONFIRM_ATTEMPTS_1591R74} попыток завершены — беру следующую строку")\n''',
     "confirm push: the end status"),
    ('''        set_tab_status(worker, "🟡", f"Ожидаю подтверждение: попытка {worker['confirm_attempt']}/6")\n''',
     '''        set_tab_status(worker, "🟡", f"Ожидаю подтверждение: попытка {worker['confirm_attempt']}/{CONFIRM_ATTEMPTS_1591R74}")\n''',
     "confirm push: next, status"),
    ('''            f"{worker['confirm_attempt']}/6: новый таймер 65 секунд.",\n''',
     '''            f"{worker['confirm_attempt']}/{CONFIRM_ATTEMPTS_1591R74}: новый таймер 65 секунд.",\n''',
     "confirm push: next, log"),
    ('''        "6 попыток подтверждения закончились — возвращаюсь на один шаг назад "\n''',
     '''        f"{CONFIRM_ATTEMPTS_1591R74} попыток подтверждения закончились — возвращаюсь на один шаг назад "\n''',
     "confirm push: back to the form, log"),
    ('''            f"[Вкладка {worker['id']}] После 6 попыток не удалось вернуться к форме. "\n''',
     '''            f"[Вкладка {worker['id']}] После {CONFIRM_ATTEMPTS_1591R74} попыток не удалось вернуться к форме. "\n''',
     "confirm push: back to the form, failure"),
)
PUSH_EDITS_R74 = ((OLD_PUSH_MARK_R74, NEW_PUSH_MARK_R74, "confirm push: marker"),
                  (OLD_PUSH_HEAD_R74, NEW_PUSH_HEAD_R74, "confirm push: helper"),
                  *PUSH_SITES_R74)
README_NOTE_R74 = ('\n\nРЕВИЗИЯ 74 (fix_package_1591.py)\nСколько push-запросов получает клиент на странице подтверждения — настройка. Раньше шесть было зашито в коде\n'
                   '(первый запрос и пять «Отправить снова» по 65 с). «⚙️ Настройки → 📲 Push»: 6 по умолчанию, можно поднять до 30\n'
                   '(BEELINE_CONFIRM_ATTEMPTS, применяется перезапуском бота). Настройка «Выгрузка по умолчанию» из r73 убрана\n'
                   '(я неверно понял просьбу). Маркер: CONFIRM_PUSH_1591R74.\n')

# Revision 75: «❔ подпись не подтверждена» is gone. After the signature the site answered 200 and the passport data
# 202 (both «принято») and then showed /registration/error; the runtime wrote the row off by the look of that page,
# without looking at the order. The order has its own link, and the site's state of it is the truth.
# - CONTRACT_LIMIT_1591R75: the site's own answer «ошибка N — превышено количество договоров, дистанционная регистрация
#   невозможна» (10.11, rows 1509 and others: signature 200, passport data 202, then /registration/error) is a refusal
#   by the client's data, not a lost eSIM and not an unconfirmed signature: the row is skipped at once with that text
#   (no six re-entries, no «❔»), recorded in error_skipped_rows.txt and told to Telegram in plain words.
# - ORDER_VERIFY_1591R75: before a row is recorded as unverified, the order is opened by its own link in a fresh
#   browser context (read-only, as the menu's link check does) and its state is read: the payment step → 💳 recorded
#   as a payment (the number is processed), the eSIM already issued → ✅ recorded as a success, the order back at its
#   first step, gone or unreadable → the row starts over (REENTER_ROW_MAX_1591R67 times) and then in a fresh page again;
#   the loop defers a row that keeps failing, it never writes it off. «❔» is written only when no page could be opened.
ORDER_VERIFY_MARKER = "ORDER_VERIFY_1591R75"
OLD_VERIFY_MARK_R75 = NEW_PUSH_MARK_R74.splitlines(keepends=True)[-1]
NEW_VERIFY_MARK_R75 = (OLD_VERIFY_MARK_R75
                       + '# ORDER_VERIFY_1591R75: the order is read by its own link before a row is written off; no «❔».\n')
CONTRACT_LIMIT_REASON_R75 = "у клиента превышено количество договоров — Билайн не даёт оформить eSIM дистанционно"
OLD_VERIFY_HEAD_R75 = '# CONFIRM_PUSH_1591R74\ndef _confirm_attempts_1591r74():\n'
NEW_VERIFY_HEAD_R75 = r'''# ORDER_VERIFY_1591R75
ORDER_VERIFY_SECONDS_1591R75 = 25
_ORDER_STATUS_KINDS_1591R75 = {"DOCS_GENERATED": "pay", "ESIM_SUCCESS": "used"}


def _order_state_1591r75(worker):
    """(kind, note) of the row's order read by its own link in a fresh browser context: "pay" the payment step,
    "used" the eSIM is issued, "start" the order is back at its first step, "unknown" nothing could be read."""
    page = worker.get("page")
    url = str(worker.get("reserved_sim_url") or getattr(page, "_reserved_sim_url", "") or "")
    context = worker.get("context")
    if not url or context is None:
        return "unknown", "нет ссылки заказа"
    fresh, probe, seen = None, None, {"status": ""}
    try:
        browser = getattr(context, "browser", None)
        fresh = browser.new_context() if browser is not None else None
        probe = (fresh or context).new_page()

        def on_response(resp):
            try:
                if "json" not in str(resp.headers.get("content-type", "")):
                    return
                if "selfreg" not in resp.url and "order" not in resp.url.lower():
                    return
                found = re.search(r'"selfregStatus"\s*:\s*"([A-Za-z_]+)"', resp.text() or "")
                if found:
                    seen["status"] = found.group(1).upper()
            except Exception:
                pass

        probe.on("response", on_response)
        probe.goto(url, wait_until="domcontentloaded", timeout=ORDER_VERIFY_SECONDS_1591R75 * 1000)
        try:
            probe.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        probe.wait_for_timeout(1500)
        body = (probe.locator("body").inner_text(timeout=2000) or "").lower().replace("\xa0", " ")
    except Exception as exc:
        return "unknown", f"{type(exc).__name__}: {str(exc)[:80]}"
    finally:
        for thing in (probe, fresh):
            try:
                if thing is not None:
                    thing.close()
            except Exception:
                pass
    status = seen["status"]
    kind = _ORDER_STATUS_KINDS_1591R75.get(status)
    if kind:
        return kind, f"selfregStatus={status}"
    if "пора оплатить" in body and "способ регистрации" not in body:
        return "pay", "экран «Теперь пора оплатить eSIM»"
    if "способ регистрации" in body or "введите данные снова" in body or "/error" in str(getattr(probe, "url", "")):
        return "start", (f"selfregStatus={status}" if status else "заказ вернулся в начало")
    return "unknown", (f"selfregStatus={status}" if status else "страница заказа не опознана")


def _restart_row_1591r75(worker, reason):
    """The row is not written off: a fresh page, the same row; the loop defers a row that keeps failing."""
    print(f"[Вкладка {worker.get('id')}] {reason}: строку не списываю — новая вкладка, та же строка "
          "(если и это не поможет, её отложат в очередь, а не потеряют).", flush=True)
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    set_tab_status(worker, "♻️", "Заказ не дошёл до оплаты — повторяю строку в новой вкладке.")
    external_heartbeat(worker, "restart_row_1591r75")
    return True


def _finish_issued_1591r75(base_dir, worker, note):
    """The site says the eSIM is issued: recorded as a success, the number is processed."""
    row_no, _, _ = row_parts(worker.get("row"))
    worker["phase"] = "SUCCESS_STOP"
    rec = write_success_record(base_dir, worker)
    remember_processed_number(base_dir, worker.get("row"))
    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_success_message(worker, rec))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить SUCCESS в очередь: {type(exc).__name__}: {exc}", flush=True)
    set_tab_status(worker, "✅", f"УСПЕХ\neSIM выпущена ({note})\nSIM: {rec.get('sim_number') or 'не найден'}")
    external_heartbeat(worker, "success_stop")
    print(f"\n[Вкладка {worker['id']}] ✅ eSIM ВЫПУЩЕНА ({note}). Строка {row_no}.\n", flush=True)
    worker["stopped"] = True
    return rec


def _verify_order_1591r75(base_dir, worker, reason):
    """True when the row was dealt with without writing it off as unverified."""
    kind, note = _order_state_1591r75(worker)
    print(f"[Вкладка {worker.get('id')}] Состояние заказа по его ссылке: {kind} ({note}).", flush=True)
    if kind == "pay":
        _finish_payment_required_1591r26(base_dir, worker, f"заказ на шаге оплаты: {note}")
        return True
    if kind == "used":
        _finish_issued_1591r75(base_dir, worker, note)
        return True
    if _reenter_row_1591r67(worker, "ORDER_" + kind.upper()):
        return True
    return _restart_row_1591r75(worker, str(reason or "")[:120])
''' + r'''

# CONTRACT_LIMIT_1591R75
CONTRACT_LIMIT_REASON_1591R75 = ''' + repr(CONTRACT_LIMIT_REASON_R75) + r'''
CONTRACT_LIMIT_TEXTS_1591R75 = ("превышено количество договоров", "дистанционная регистрация невозможна")


def _contract_limit_1591r75(worker):
    """The reason when the error page says the client has too many contracts (a refusal by his data), else ""."""
    try:
        body = (worker["page"].locator("body").inner_text(timeout=1500) or "").lower().replace("\xa0", " ")
    except Exception:
        return ""
    return CONTRACT_LIMIT_REASON_1591R75 if any(text in body for text in CONTRACT_LIMIT_TEXTS_1591R75) else ""


def _finish_contract_limit_1591r75(base_dir, worker, reason):
    """The row is skipped at once (a new tab, the number is processed, error_skipped_rows.txt) and Telegram is told in
    plain words that this is the client's refusal, not a lost eSIM. False when no new tab could be opened."""
    row_no, active_value, second_value = row_parts(worker.get("row"))
    total, tab_id = worker.get("total_rows") or "?", worker.get("id")
    print(f"[Вкладка {tab_id}] Сайт пишет «превышено количество договоров, дистанционная регистрация невозможна»: "
          f"строка {row_no} — {reason}. Это отказ по данным клиента, eSIM не потеряна; повторять бессмысленно.", flush=True)
    if not _error_skip_final(worker, reason):
        remember_processed_number(base_dir, worker.get("row"))
        return False
    queue = worker.get("success_queue")
    if queue is not None:
        try:
            queue.put("\n".join([
                "#лимит_договоров",
                f"🚫 Строка {row_no}/{total} · Вкладка {tab_id}: у клиента превышено количество договоров",
                "Билайн не даёт оформить eSIM дистанционно (сайт: «превышено количество договоров, дистанционная регистрация невозможна»).",
                "Это отказ по данным строки, не сбой бота: заказ не потерян, номер пропущен, повторять не нужно.",
                f"Исходные данные: {active_value} | {second_value}"]))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить LIMIT в очередь: {type(exc).__name__}: {exc}", flush=True)
    return True


''' + OLD_VERIFY_HEAD_R75
OLD_LIMIT_NEEDLES_R75 = '    ("не совпадают с данными", "данные не совпадают с базой оператора"),\n)\n'
NEW_LIMIT_NEEDLES_R75 = (OLD_LIMIT_NEEDLES_R75[:-2]
                         + '    ("превышено количество договоров", ' + repr(CONTRACT_LIMIT_REASON_R75) + '),  # CONTRACT_LIMIT_1591R75\n'
                         + '    ("дистанционная регистрация невозможна", ' + repr(CONTRACT_LIMIT_REASON_R75) + '),\n)\n')
OLD_VERIFY_HOOK_R75 = ('    if _reenter_row_1591r67(worker, "PERSONAL_TOKEN_ERROR" if "PERSONAL_TOKEN" in str(reason) else ""):\n'
                       '        return None\n')
NEW_VERIFY_HOOK_R75 = ('    # ORDER_VERIFY_1591R75: the order is read by its own link first: the payment step is 💳, an issued eSIM is ✅,\n'
                       '    # anything else starts the row over; the row is written off as unverified only when no page could be opened.\n'
                       '    # CONTRACT_LIMIT_1591R75: «превышено количество договоров» is the client\'s refusal: skip at once, say so plainly.\n'
                       '    limit = (globals().get("_contract_limit_1591r75") or (lambda w: ""))(worker)\n'
                       '    if limit:\n'
                       '        if _finish_contract_limit_1591r75(base_dir, worker, limit):\n'
                       '            return None\n'
                       '        reason = limit\n'
                       '    elif (globals().get("_verify_order_1591r75") or (lambda b, w, r: False))(base_dir, worker, reason):\n'
                       '        return None\n'
                       + OLD_VERIFY_HOOK_R75)
VERIFY_EDITS_R75 = ((OLD_VERIFY_MARK_R75, NEW_VERIFY_MARK_R75, "order verify: marker"),
                    (OLD_VERIFY_HEAD_R75, NEW_VERIFY_HEAD_R75, "order verify: helpers"),
                    (OLD_LIMIT_NEEDLES_R75, NEW_LIMIT_NEEDLES_R75, "contract limit: the operator's refusal texts"),
                    (OLD_VERIFY_HOOK_R75, NEW_VERIFY_HOOK_R75, "order verify: before the unverified record"))
README_NOTE_R75 = ('\n\nРЕВИЗИЯ 75 (fix_package_1591.py)\nОшибка сайта «превышено количество договоров, дистанционная регистрация невозможна» (11.10, строки 1509 и другие:\n'
                   'подпись 200, паспортные данные 202, потом /registration/error) — отказ по данным клиента, а не потеря eSIM. Строка\n'
                   'пропускается сразу (без шести повторов), номер помечается обработанным, в Telegram — понятное сообщение\n'
                   '«🚫 у клиента превышено количество договоров». Маркер: CONTRACT_LIMIT_1591R75.\n'
                   '«❔ подпись не подтверждена» убрана. Сайт отвечал на подпись 200 и на паспортные данные 202 («принято»), а потом\n'
                   'показывал /registration/error, и бот списывал строку по виду страницы, не глядя на заказ. Теперь перед этим заказ\n'
                   'открывается по его собственной ссылке (в чистом контексте, только чтение): шаг оплаты — строка 💳, eSIM выпущена —\n'
                   'строка ✅, заказ вернулся в начало или не читается — строка вводится заново (до 6 раз), потом новой вкладкой; строку,\n'
                   'которая так и не проходит, очередь откладывает, а не теряет. «❔» пишется только если ни одну страницу открыть не\n'
                   'удалось. Маркер: ORDER_VERIFY_1591R75.\n')

# Revision 76: why the site shows «введите данные снова — с заказом всё хорошо» on the confirmation screen (about 160
# times in 14 h on one server, 212 of 250 cases within 10 s after the first «Отправить снова», the same rows again and
# again). The bot kept the site's answers only around «Подписать договор»; on the confirmation screen it kept nothing,
# so the reason was a guess.
# - CONFIRM_TRACE_1591R76: from the start of a row the page keeps the site's own answers (JSON, POST, HTTP errors of
#   beeline; no pictures, scripts or counters), the bot's «Отправить снова» clicks are marked among them. When an error
#   page opens, the error tab itself is looked at: its own requests (2.5 s), its text, and the order status asked from
#   that tab (the same getselfregstatus GET the site makes, with the tab's cookies, as the menu's link check does).
#   All of it goes to confirm_errors.jsonl, one journal line names the status and the last answers with their codes
#   (selfregStatus, codeValue, message). night_report.py confirm sums them up. Nothing in the bot's behaviour changes.
CONFIRM_TRACE_MARKER = "CONFIRM_TRACE_1591R76"
OLD_TRACE_MARK_R76 = NEW_VERIFY_MARK_R75.splitlines(keepends=True)[-1]
NEW_TRACE_MARK_R76 = (OLD_TRACE_MARK_R76
                      + '# CONFIRM_TRACE_1591R76: the site\'s answers before an error page are kept (confirm_errors.jsonl).\n')
OLD_TRACE_HEAD_R76 = '# ORDER_VERIFY_1591R75\nORDER_VERIFY_SECONDS_1591R75 = 25\n'
NEW_TRACE_HEAD_R76 = r'''# CONFIRM_TRACE_1591R76
CONFIRM_TRACE_MAX_1591R76 = 80
_CONFIRM_TRACE_SKIP_1591R76 = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|css|js|woff2?|ttf|ico|mp4)(\?|$)|metrika|analytics|google|flocktory|yandex|gtm|chatwidget",
    re.I,
)
_CONFIRM_TRACE_CODES_1591R76 = re.compile(
    r'"(selfregStatus|codeValue|errorCode|errorMessage|message|error|status|state|reason)"\s*:\s*"([^"]{1,80})"')


def _confirm_trace_start_1591r76(page, note):
    """From the start of a row the page keeps the site's answers (JSON, POST, HTTP errors) in a ring."""
    if page is None:
        return
    ring = getattr(page, "_confirm_trace_1591r76", None)
    if ring is None:
        ring = []

        def on_response(resp):
            try:
                url = str(resp.url or "")
                if "beeline" not in url or _CONFIRM_TRACE_SKIP_1591R76.search(url):
                    return
                method, status = str(resp.request.method), int(resp.status)
                kind = str(resp.headers.get("content-type", "") or "")
                if "json" not in kind and status < 400 and method == "GET":
                    return
                if "getselfregstatus" in url.lower():
                    setattr(page, "_status_url_1591r76", url)  # the tab's own status request, asked again on an error
                item = {"t": time.strftime("%H:%M:%S"), "method": method, "status": status,
                        "url": re.sub(r"[?#].*", "", url)[:200]}
                try:
                    item["body"] = re.sub(r"\s+", " ", str(resp.text() or ""))[:700]
                except Exception as exc:
                    item["body"] = f"<{type(exc).__name__}>"
                ring.append(item)
                del ring[:-CONFIRM_TRACE_MAX_1591R76]
            except Exception:
                pass

        try:
            page.on("response", on_response)
            setattr(page, "_confirm_trace_1591r76", ring)
        except Exception:
            return
    ring.clear()
    ring.append({"t": time.strftime("%H:%M:%S"), "mark": str(note)[:120]})


def _confirm_trace_mark_1591r76(page, note):
    ring = getattr(page, "_confirm_trace_1591r76", None)
    if ring is not None:
        ring.append({"t": time.strftime("%H:%M:%S"), "mark": str(note)[:120]})


def _confirm_trace_brief_1591r76(item):
    """«GET getselfregstatus → 200 selfregStatus=…» or «— нажата «Отправить снова»»."""
    if "mark" in item:
        return f"{item.get('t')} — {item['mark']}"
    parts = [p for p in str(item.get("url") or "").split("/") if p]
    codes = [f"{k}={v}" for k, v in _CONFIRM_TRACE_CODES_1591R76.findall(str(item.get("body") or ""))
             if v.strip() and v.lower() not in ("null", "ok")][:3]
    return (f"{item.get('t')} {item.get('method')} {parts[-1] if parts else '?'} → {item.get('status')}"
            + (f" {', '.join(codes)}" if codes else ""))


_TAB_STATUS_JS_1591R76 = """async (u) => {
  try {
    const r = await fetch(u, {credentials: 'include', headers: {'accept': 'application/json'}});
    return {status: r.status, body: (await r.text()).slice(0, 1500)};
  } catch (e) { return {status: 0, body: String(e).slice(0, 200)}; }
}"""


def _tab_status_1591r76(page):
    """The error tab itself asks the site for its order status (the same GET the site's own page makes)."""
    url = str(getattr(page, "_status_url_1591r76", "") or "/v1/esim-selfreg/v2/getselfregstatus/")
    try:
        got = page.evaluate(_TAB_STATUS_JS_1591R76, url) or {}
    except Exception as exc:
        got = {"status": 0, "body": type(exc).__name__}
    return {"t": time.strftime("%H:%M:%S"), "method": "GET", "url": re.sub(r"[?#].*", "", url)[:200],
            "status": int(got.get("status") or 0), "body": re.sub(r"\s+", " ", str(got.get("body") or ""))[:900],
            "tab_check": True}


def _confirm_trace_dump_1591r76(worker, reason):
    """An error page: the site's answers of this row, the error page's own requests and the order status asked from
    the error tab itself go to confirm_errors.jsonl; the last ones and the status to the journal."""
    page = worker.get("page")
    ring = getattr(page, "_confirm_trace_1591r76", None)
    if not ring:  # no trace for this page, or this error page is already written
        return None
    try:
        page.wait_for_timeout(2500)  # the error page's own requests
    except Exception:
        pass
    tab_status = _tab_status_1591r76(page)
    try:
        page_text = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1500) or "")[:400]
    except Exception:
        page_text = ""
    row_no, _, _ = row_parts(worker.get("row"))
    try:
        url = str(page.url or "")
    except Exception:
        url = ""
    rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": worker.get("id"), "row": row_no,
           "attempt": worker.get("confirm_attempt"), "phase": worker.get("phase"), "reason": str(reason)[:120],
           "last_step": worker.get("last_progress_label"), "url": re.sub(r"[?#].*", "", url),
           "page_text": page_text, "tab_status": tab_status, "answers": list(ring)}
    base_dir = worker.get("base_dir") or Path(__file__).resolve().parent
    try:
        with (Path(base_dir) / "confirm_errors.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[Вкладка {worker.get('id')}] confirm_errors.jsonl не записан: {type(exc).__name__}: {exc}", flush=True)
    last = [_confirm_trace_brief_1591r76(item) for item in rec["answers"][-6:]]
    print(f"[Вкладка {worker.get('id')}] Статус заказа во вкладке с ошибкой (строка {row_no}): "
          f"{_confirm_trace_brief_1591r76(tab_status)}. Ответы сайта перед этим: " + " | ".join(last), flush=True)
    ring.clear()
    return rec


''' + OLD_TRACE_HEAD_R76
OLD_TRACE_START_R76 = ('        f"\\n[Вкладка {tab_id}] Обрабатываю строку {line_number}, "\n'
                       '        f"номер заканчивается на {active_digits[-4:]}.",\n'
                       '        flush=True,\n'
                       '    )\n')
NEW_TRACE_START_R76 = (OLD_TRACE_START_R76
                       + '    # CONFIRM_TRACE_1591R76: the site\'s answers of this row are kept (the push request goes on «Продолжить»)\n'
                       + '    (globals().get("_confirm_trace_start_1591r76") or (lambda p, n: None))(page, f"строка {line_number}")\n')
OLD_TRACE_RESEND_R76 = '    clicked = try_click_resend_once(page, worker["id"])\n'
NEW_TRACE_RESEND_R76 = (OLD_TRACE_RESEND_R76
                        + '    if clicked:  # CONFIRM_TRACE_1591R76\n'
                        + '        (globals().get("_confirm_trace_mark_1591r76") or (lambda p, n: None))(\n'
                        + '            page, f"нажата «Отправить снова» после попытки {worker.get(\'confirm_attempt\')}")\n')
OLD_TRACE_BOX_R76 = '    """Сохраняет визуальное и техническое состояние проблемной вкладки."""\n'
NEW_TRACE_BOX_R76 = (OLD_TRACE_BOX_R76
                     + '    if "registration_error" in str(reason) or str(reason) == "error_final_skip":  # CONFIRM_TRACE_1591R76\n'
                     + '        try:\n'
                     + '            (globals().get("_confirm_trace_dump_1591r76") or (lambda w, r: None))(worker, reason)\n'
                     + '        except Exception:\n'
                     + '            pass\n')
TRACE_EDITS_R76 = ((OLD_TRACE_MARK_R76, NEW_TRACE_MARK_R76, "confirm trace: marker"),
                   (OLD_TRACE_HEAD_R76, NEW_TRACE_HEAD_R76, "confirm trace: helpers"),
                   (OLD_TRACE_START_R76, NEW_TRACE_START_R76, "confirm trace: row start"),
                   (OLD_TRACE_RESEND_R76, NEW_TRACE_RESEND_R76, "confirm trace: «Отправить снова» mark"),
                   (OLD_TRACE_BOX_R76, NEW_TRACE_BOX_R76, "confirm trace: dump on an error page"))
README_NOTE_R76 = ('\n\nРЕВИЗИЯ 76 (fix_package_1591.py)\nПочему на экране подтверждения сайт пишет «введите данные снова — с заказом всё хорошо» (сотни раз за ночь,\n'
                   'почти всегда сразу после первого «Отправить снова»), было не видно: ответы сайта бот записывал только при подписи.\n'
                   'Теперь с начала строки вкладка хранит ответы сайта (JSON, POST, ошибки HTTP; без картинок и счётчиков), нажатия\n'
                   '«Отправить снова» отмечены среди них. Когда открывается страница ошибки, они пишутся в confirm_errors.jsonl, а в\n'
                   'журнал — строка с последними ответами и их кодами (selfregStatus, codeValue, message). Сама вкладка с ошибкой\n'
                   'тоже проверяется: её текст, её запросы и статус заказа, запрошенный прямо из неё (как в проверке ссылок). Сводка:\n'
                   'night_report.py confirm. Поведение бота не меняется. Маркер: CONFIRM_TRACE_1591R76.\n')

# Experiment «browsers8»: a separate build for a big test server (32 vCPU / 64 GB), never the
# production one. The cap of BEELINE_BROWSERS rises from 4 to 8 Chromium (up to 32 tabs with
# BEELINE_TABS_PER_BROWSER=4); everything else is the same revision. Built with
# FIX_1591_EXPERIMENT=browsers8 and published as beeline_integrated_io_15_91_rNN_exp8 (lite based);
# update.sh and fresh_install.sh never pick it unless BUILD=exp8 or the server already runs it.
EXPERIMENT = (os.environ.get("FIX_1591_EXPERIMENT") or "").strip()
if EXPERIMENT not in {"", "browsers8"}:
    raise SystemExit(f"FIX_1591_EXPERIMENT={EXPERIMENT!r}: the only experiment is browsers8")
EXPERIMENT_MARKER = "EXPERIMENT_BROWSERS8_1591"
OLD_BROWSER_CAP_EXP = ('        value = default\n    return min(max(value, 1), 4)\n\n\n'
                       'BROWSER_COUNT = _browser_count_1591r34()  # TWO_BROWSERS_1591R28: Chromium instances, TABS_PER_BROWSER tabs each\n')
NEW_BROWSER_CAP_EXP = ('        value = default\n    return min(max(value, 1), 8)  # EXPERIMENT_BROWSERS8_1591: up to 8 Chromium (32 tabs) on a big test server\n\n\n'
                       'BROWSER_COUNT = _browser_count_1591r34()  # TWO_BROWSERS_1591R28: Chromium instances, TABS_PER_BROWSER tabs each\n')
OLD_START_LINE_EXP = NEW_TARIFF_START_R42[len(OLD_TARIFF_START_R42):]   # the «Тариф: …» startup line of r42
NEW_START_LINE_EXP = OLD_START_LINE_EXP + '    print(f"ЭКСПЕРИМЕНТ browsers8: лимит BEELINE_BROWSERS поднят до 8 Chromium; сейчас {BROWSER_COUNT} × {TABS_PER_BROWSER} вкладок.", flush=True)  # EXPERIMENT_BROWSERS8_1591\n'
README_NOTE_EXP = ('\n\nЭКСПЕРИМЕНТ browsers8 (fix_package_1591.py, FIX_1591_EXPERIMENT=browsers8)\nОтдельная сборка для мощного тестового сервера: лимит BEELINE_BROWSERS поднят с 4 до 8 Chromium\n'
                   '(до 32 вкладок при BEELINE_TABS_PER_BROWSER=4). Всё остальное — та же ревизия. В рабочие серверы\n'
                   'не ставится: update.sh берёт её только при BUILD=exp8 или если она уже стоит. Маркер: EXPERIMENT_BROWSERS8_1591.\n')
README_NOTE_R10 = '''

РЕВИЗИЯ 10 (fix_package_1591.py)
Скорость матчера. На сервере с ослабленным CPU одна капча занимала около 4 минут: четыре
прохода shape_costs по ~50 секунд. В пакет добавлен symbol_matching.py версии 14.1 —
тот же алгоритм 14.0 (пороги, дескрипторы, 36 поворотов, выбор пар не менялись), но:
shape_costs сравнивает повёрнутого кандидата со всеми образцами матричным произведением,
а не циклом по образцам и пикселям; thin() берёт решение Чжана-Суэня из таблицы 256
окрестностей и работает в рамке маски; каждая маска утончается один раз (native и affine
дескрипторы делят скелет); проходы NATIVE и CLEAN сравнивают одних и тех же кандидатов,
поэтому делят один обход поворотов; одинаковые маски порогов не пересчитывают regions().
Скелеты и области совпадают побитно, стоимости — с точностью float32 (~1e-6), выбранные
пары те же. install.py принимает только серверный symbol_matching.py 14.0 (sha256
915368d6…) или уже установленный 14.1; иначе останавливается, ничего не меняя.
Маркер: MATCHER_SPEED_1591R10. local_matcher.py не трогается.
'''
OVERLAY_HELPER_R7 = r'''# OVERLAY_DISMISS_1591R6 / TARIFF_BY_NAME_1591R7
_MODAL_DIALOG_SELECTOR = '[role="dialog"][aria-modal="true"]'
_CHOOSE_BUTTON_RE = re.compile(r"^\s*выбрать\s*$", re.I)


def _blocking_dialog_indexes(page, keep_text=None, keep_selector=None):
    """Indexes of visible modal dialogs that do NOT contain what we are about to click."""
    return list(page.evaluate("""([keepText, keepSelector]) => {
        const out = [];
        [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].forEach((el, i) => {
            const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
            if (!(r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden')) return;
            if (keepSelector && el.querySelector(keepSelector)) return;
            if (keepText && (el.innerText || '').includes(keepText)) return;
            out.push(i);
        });
        return out;
    }""", [keep_text or "", keep_selector or ""]) or [])


def _visible_modal_dialogs(page):
    return len(_blocking_dialog_indexes(page))


def dismiss_blocking_overlays(page, attempts=3, keep_text=None, keep_selector=None):
    """Close a portal modal that intercepts clicks; never the dialog we need.

    Order: a visible close button inside the dialog, then Escape; as a last resort the
    dialog stops intercepting pointer events. The DOM is never removed, the basket is kept.
    A dialog containing keep_text or an element matching keep_selector is left untouched.
    Returns True when no blocking dialog is visible afterwards.
    """
    for _ in range(attempts):
        try:
            blocking = _blocking_dialog_indexes(page, keep_text, keep_selector)
        except Exception:
            return True
        if not blocking:
            return True
        closed = False
        dialog = page.locator(_MODAL_DIALOG_SELECTOR).nth(blocking[-1])
        for close_button in (
            dialog.get_by_role("button", name=re.compile(r"закрыть|close|✕|×", re.I)),
            dialog.locator('button[aria-label*="акрыть" i], button[aria-label*="close" i], [data-testid*="close" i]'),
        ):
            try:
                if close_button.count() > 0:
                    close_button.first.click(timeout=1500, no_wait_after=True)
                    closed = True
                    break
            except Exception:
                pass
        if not closed and not keep_text and not keep_selector:
            # Escape would close the protected dialog too; use it only when nothing is protected.
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass
    try:
        blocking = _blocking_dialog_indexes(page, keep_text, keep_selector)
        if not blocking:
            return True
        page.evaluate("""(indexes) => {
            const all = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
            indexes.forEach(i => { if (all[i]) all[i].style.pointerEvents = 'none'; });
        }""", blocking)
        print("Модальное окно не закрылось; снял перехват кликов, DOM не трогал.", flush=True)
    except Exception:
        pass
    return False


def _tariff_choose_button(page, diagnostic=None, timeout=10000):
    """«выбрать» inside the card titled TARIFF_NAME; the card order is never assumed."""
    title = page.get_by_text(TARIFF_NAME, exact=True).first
    try:
        title.wait_for(state="visible", timeout=timeout)
        card = title.locator(
            "xpath=ancestor::*[.//button[normalize-space(.)='выбрать' or normalize-space(.)='Выбрать']][1]"
        )
        button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)
        if button.count() > 0:
            return button.first
    except Exception:
        pass
    try:
        titles = page.locator("text=/подписка/i").all_inner_texts()[:10]
        choose_count = page.get_by_role("button", name=_CHOOSE_BUTTON_RE).count()
    except Exception:
        titles, choose_count = [], -1
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_card_not_found", tariff=TARIFF_NAME, titles=titles, choose_buttons=choose_count)
        except Exception:
            pass
    print(
        f"Карточка «{TARIFF_NAME}» с кнопкой «выбрать» не найдена; на экране: {titles}, "
        f"кнопок «выбрать»: {choose_count}",
        flush=True,
    )
    raise RuntimeError(
        f"RECOVERABLE_RESTART_ROW: карточка тарифа «{TARIFF_NAME}» с кнопкой «выбрать» не найдена."
    )


'''
OLD_CHOOSE_LOOP_R6 = '''        for choose_attempt in range(1, 4):
            dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
            choose_button = page.get_by_role(
                "button", name="выбрать", exact=True
            ).nth(1)
'''
NEW_CHOOSE_LOOP_R7 = '''        for choose_attempt in range(1, 4):
            dismiss_blocking_overlays(page, keep_text=TARIFF_NAME)  # OVERLAY_DISMISS_1591R6
            choose_button = _tariff_choose_button(page, diagnostic)  # TARIFF_BY_NAME_1591R7
'''
OLD_ESIM_DISMISS_R6 = '''        dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
        radio = page.locator('input#esim[name="sim"]')
'''
NEW_ESIM_DISMISS_R7 = '''        dismiss_blocking_overlays(page, keep_selector='input#esim[name="sim"]')  # OVERLAY_DISMISS_1591R6
        radio = page.locator('input#esim[name="sim"]')
'''
README_NOTE_R7 = '''

РЕВИЗИЯ 7 (fix_package_1591.py)
Выбор тарифа по названию. Раньше нажималась ВТОРАЯ кнопка «выбрать» на экране «выберите
тариф»; сайт поменял порядок карточек, и вторая кнопка стала принадлежать платной
«подписка bee HIT», а bee START оказалась первой. Теперь ищется карточка с текстом
TARIFF_NAME («подписка bee START») и нажимается кнопка «выбрать» внутри неё; при
неудаче в лог пишутся реальные названия карточек и число кнопок. Закрыватель модальных
окон из ревизии 6 больше не трогает диалог, в котором находится нужный элемент
(экран выбора тарифа сам является диалогом с крестиком); Escape не нажимается, когда
есть защищаемый диалог. Маркер: TARIFF_BY_NAME_1591R7.
'''
OVERLAY_HELPER_R6 = r'''# OVERLAY_DISMISS_1591R6
_MODAL_DIALOG_SELECTOR = '[role="dialog"][aria-modal="true"]'


def _visible_modal_dialogs(page):
    return int(page.evaluate("""() => [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')]
        .filter(el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'; }).length""") or 0)


def dismiss_blocking_overlays(page, attempts=3):
    """Close a portal modal that intercepts clicks on the basket page.

    Order: a visible close button inside the dialog, then Escape; as a last resort the
    dialog stops intercepting pointer events. The DOM is never removed, the basket is kept.
    Returns True when no modal dialog is visible afterwards.
    """
    for _ in range(attempts):
        try:
            if not _visible_modal_dialogs(page):
                return True
        except Exception:
            return True
        closed = False
        dialog = page.locator(_MODAL_DIALOG_SELECTOR).last
        for close_button in (
            dialog.get_by_role("button", name=re.compile(r"закрыть|close|✕|×", re.I)),
            dialog.locator('button[aria-label*="акрыть" i], button[aria-label*="close" i], [data-testid*="close" i]'),
        ):
            try:
                if close_button.count() > 0:
                    close_button.first.click(timeout=1500, no_wait_after=True)
                    closed = True
                    break
            except Exception:
                pass
        if not closed:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass
    try:
        if not _visible_modal_dialogs(page):
            return True
        page.evaluate("""() => document.querySelectorAll('[role="dialog"][aria-modal="true"]')
            .forEach(el => { el.style.pointerEvents = 'none'; })""")
        print("Модальное окно не закрылось; снял перехват кликов, DOM не трогал.", flush=True)
    except Exception:
        pass
    return False


'''
OLD_SELECT_ESIM_ATTEMPT = '''        print(f"Выбор eSIM: попытка {attempt}/3...", flush=True)
        radio = page.locator('input#esim[name="sim"]')
        try:
            radio.wait_for(state="visible", timeout=10000)
            expect(radio).to_be_enabled(timeout=10000)
            # При повторном рендере locator находит актуальный input.
            if not esim_state(page)["selected"]:
                radio.click(timeout=5000)
        except PlaywrightTimeoutError:
            print("Нажатие не подтверждено; проверяю состояние переключателя.")
'''
NEW_SELECT_ESIM_ATTEMPT = '''        print(f"Выбор eSIM: попытка {attempt}/3...", flush=True)
        dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
        radio = page.locator('input#esim[name="sim"]')
        try:
            radio.wait_for(state="visible", timeout=10000)
            expect(radio).to_be_enabled(timeout=10000)
            # При повторном рендере locator находит актуальный input.
            if not esim_state(page)["selected"]:
                radio.click(timeout=5000)
        except PlaywrightTimeoutError:
            print("Нажатие не подтверждено; проверяю состояние переключателя.")
        if not esim_state(page)["selected"]:
            # The pointer may still be intercepted by a portal layer: click through it.
            try:
                radio.click(timeout=3000, force=True, no_wait_after=True)
            except Exception:
                pass
        if not esim_state(page)["selected"]:
            try:
                page.evaluate("""() => {
                    const el = document.querySelector('input#esim[name="sim"]');
                    if (!el) return;
                    const label = el.closest('label');
                    if (label) label.click(); else el.click();
                    if (!el.checked) {
                        el.checked = true;
                        for (const t of ['input', 'change']) el.dispatchEvent(new Event(t, {bubbles: true}));
                    }
                }""")
            except Exception:
                pass
'''
OLD_TARIFF_CLICK = '''            last_error = None
            for candidate in candidates:
                try:
                    expect(candidate.first).to_be_visible(timeout=20000)
                    candidate.first.click(timeout=15000, no_wait_after=True)
                    return
                except (PlaywrightTimeoutError, AssertionError) as exc:
                    last_error = exc
'''
NEW_TARIFF_CLICK = '''            last_error = None
            dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
            for candidate in candidates:
                try:
                    expect(candidate.first).to_be_visible(timeout=20000)
                    try:
                        candidate.first.click(timeout=15000, no_wait_after=True)
                    except PlaywrightTimeoutError:
                        # The button is ready; a portal modal intercepts the pointer.
                        dismiss_blocking_overlays(page)
                        candidate.first.click(timeout=15000, no_wait_after=True, force=True)
                    return
                except (PlaywrightTimeoutError, AssertionError) as exc:
                    last_error = exc
'''
OLD_CHOOSE_LOOP = '''        for choose_attempt in range(1, 4):
            choose_button = page.get_by_role(
                "button", name="выбрать", exact=True
            ).nth(1)
'''
NEW_CHOOSE_LOOP = '''        for choose_attempt in range(1, 4):
            dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
            choose_button = page.get_by_role(
                "button", name="выбрать", exact=True
            ).nth(1)
'''
OLD_CDP_DEF = "def _close_cdp_page_for_worker(cdp_url, info, timeout=8):\n"
CDP_HEAD_R6 = '''def _close_cdp_page_for_worker(cdp_url, info, timeout=20, attempts=2):
    """OVERLAY_DISMISS_1591R6: a Chromium busy with orphan pages needs more than 8 s;
    one real close attempt is retried once. Refusals (guard, no window_name) are final.
    The caller already refuses to create a replacement while the old page is open."""
'''
CDP_TAIL_R6 = '''
    if _io1591.guarded(info or {}) or not str((info or {}).get("window_name") or "").strip():
        return _once(cdp_url, info, timeout=timeout)
    import time as _time
    for attempt in range(1, attempts + 1):
        try:
            if _once(cdp_url, info, timeout=timeout):
                return True
        except Exception:
            pass
        if attempt < attempts:
            _time.sleep(2)
    return False
'''
README_NOTE_R6 = '''

РЕВИЗИЯ 6 (fix_package_1591.py)
Портальное модальное окно (role="dialog" aria-modal="true", «подбор номера») стало
перекрывать корзину: клики Playwright по eSIM и кнопкам тарифа перехватывались, и
строка бесконечно уходила в same-row restart. Добавлен dismiss_blocking_overlays():
кнопка закрытия внутри диалога, затем Escape, в крайнем случае снятие перехвата
кликов без удаления DOM. Вызывается перед «изменить», перед каждой попыткой «выбрать»
и перед каждой попыткой выбора eSIM; для eSIM добавлены клик force=True и JS-fallback.
Таймаут закрытия вкладки через CDP увеличен с 8 до 20 с плюс одна повторная попытка.
Маркер: OVERLAY_DISMISS_1591R6. Изменены select_esim, run_registration (только
click_tariff_change и цикл «выбрать») и _close_cdp_page_for_worker (имя и вызовы прежние).
'''
MISSION_RULE_R5 = (
    "\n\nПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5): /registration/error — не успех, "
    "но и не вечное ожидание. Сначала детальный анализ страницы (DOM, текст ошибки, console/network) "
    "и мини-отчёт. После отчёта error-вкладка закрывается и открывается новая автоматически, без отдельного подтверждения: "
    "runtime делает это сразу после твоего отчёта и повторяет ту же строку один раз. "
    "При повторной ошибке на той же строке строка пропускается без нового анализа, worker берёт "
    "следующую. Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload "
    "остаётся только для SUCCESS_GUARD.")
AGENT_ERROR_BLOCK_R5 = '''ERROR SUPERVISOR:
- /registration/error НИКОГДА не является success.
- Сначала самостоятельно изучи DOM, видимый текст, console/network и последние ответы API.
  Определи конкретную причину и, если это безопасно, попробуй исправить на текущей странице.
- Затем отправь мини-отчёт: причина, что проверил, что попробовал, результат, URL.
- После детального анализа и отчёта error-вкладка закрывается и открывается новая
  АВТОМАТИЧЕСКИ, без отдельного подтверждения: runtime делает это сразу после твоего
  отчёта и повторяет ту же строку один раз. При повторной ошибке на той же строке
  строка пропускается, worker переходит к следующей.
- Из-за error worker никогда не теряется: слот всегда получает новую вкладку.
- Запрет close/restart/reload/back/navigate действует только на SUCCESS GUARD.

'''
QUEUE_ERROR_TEXT_R5 = '''    text = (
        f"[AUTO_ERROR_ASSIST TAB {tab_id}] "
        "После mobile-id-auth открылась /registration/error. Это НЕ success. "
        "Сначала автономно проанализируй текущую physical-вкладку: DOM, видимый текст "
        "ошибки, DevTools console и network, последние запросы/ответы и состояние формы. "
        "Определи конкретную причину и, если это безопасно, попробуй исправить её на этой "
        "странице. Затем ОБЯЗАТЕЛЬНО отправь мини-отчёт: причина, что проверил, что "
        "попробовал, результат, URL. Сразу после твоего отчёта runtime автоматически, без "
        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и повторит строку один раз; "
        "при повторной ошибке строка будет пропущена. Worker при этом не теряется. "
        "Сам вкладку не закрывай: это сделает runtime после отчёта. "
        f"Причина вызова: {reason}. URL: {url}"
    )
'''
TICK_ERROR_R5 = r'''# ERROR_RECOVERY_1591R5
ERROR_ASSIST_MAX_SECONDS = 300
ERROR_SKIP_DWELL_SECONDS = 15
ERROR_ROW_MAX_ATTEMPTS = 2


def _error_row_key(worker):
    row = worker.get("row")
    try:
        return _row_number_value(row) or str(row)
    except Exception:
        return str(row)


def _error_analysis_delivered(worker):
    state = (worker.get("auto_assist_state") or {}).get("ERROR") or {}
    if int(state.get("count") or 0) < 1:
        return False
    try:
        return not _auto_assist_pending("ERROR", worker.get("id") or 0)
    except Exception:
        return True


def _error_recover(base_dir, worker, reason):
    """Close the error page, open a fresh one; retry the row once, then skip it.

    Runs without user permission. A worker slot is never stopped because of an error.
    """
    key = _error_row_key(worker)
    counts = worker.setdefault("error_retry_counts", {})
    counts[key] = int(counts.get(key) or 0) + 1
    attempt = counts[key]
    try:
        capture_blackbox(worker, "error_recovery")
    except Exception:
        pass
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        print(f"[Вкладка {worker['id']}] ERROR RECOVERY: новая вкладка не создана ({reason}).", flush=True)
        return False
    if attempt < ERROR_ROW_MAX_ATTEMPTS:
        set_tab_status(
            worker, "♻️",
            f"registration/error: {reason}. Вкладка закрыта, открыта новая; "
            f"повторяю строку (попытка {attempt + 1}).",
        )
        external_heartbeat(worker, "error_retry_same_row")
        return True
    # Second error on the same row: skip it; the next row starts on the fresh page.
    try:
        with (Path(base_dir) / "error_skipped_rows.txt").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{key}\t{reason}\n")
    except Exception:
        pass
    try:
        chat = str(load_telegram_config().get("chat_id") or "")
        if chat:
            _io1591.enqueue_notice(
                globals(), chat,
                f"⏭ Вкладка {worker['id']}: строка {key} пропущена после повторной "
                f"registration/error ({reason}). Worker продолжает со следующей строкой.",
            )
    except Exception:
        pass
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена после повторной registration/error. Беру следующую.")
    external_heartbeat(worker, "error_row_skipped")
    return True


def tick_error_assist(base_dir, worker):
    page = worker["page"]
    worker["error_guard"] = True
    now = monotonic()
    if not worker.get("error_assist_entered_at"):
        worker["error_assist_entered_at"] = now
    entered = float(worker["error_assist_entered_at"])

    if page.is_closed():
        # A closed error page never costs the worker slot: open a fresh page and go on.
        _error_recover(base_dir, worker, "error-страница закрыта извне")
        return

    # If Operator safely repaired the page and it becomes a real contract page,
    # promote it into the immutable SUCCESS GUARD.
    if _post_auth_contract_page(page) and not _post_auth_error_page(page):
        worker["error_guard"] = False
        worker["error_assist_entered_at"] = None
        enter_success_guard(
            worker,
            "DeepSeek/сайт вывел error-state на страницу договора",
        )
        return

    key = _error_row_key(worker)
    if int((worker.get("error_retry_counts") or {}).get(key) or 0) >= ERROR_ROW_MAX_ATTEMPTS - 1:
        # Repeated error on the same row: no second analysis; skip after a short dwell.
        external_heartbeat(worker, "error_repeat_skip_pending")
        if now - entered >= ERROR_SKIP_DWELL_SECONDS:
            _error_recover(base_dir, worker, "повторная ошибка регистрации на той же строке")
        return

    queue_error_assist(
        worker,
        "registration/error открыта; проанализируй DOM/console/network и отправь отчёт",
    )
    external_heartbeat(worker, "error_assist_observing")
    if _error_analysis_delivered(worker):
        _error_recover(base_dir, worker, "детальный анализ завершён")
    elif now - entered >= ERROR_ASSIST_MAX_SECONDS:
        _error_recover(base_dir, worker, "анализ не получен за отведённое время")
'''
README_NOTE_R5 = '''

РЕВИЗИЯ 5 (fix_package_1591.py)
Правило ошибки регистрации (ERROR_RECOVERY_1591R5). После детального анализа и отчёта
DeepSeek runtime автоматически, без отдельного подтверждения, закрывает error-вкладку, открывает новую и
повторяет ту же строку один раз; при повторной ошибке на той же строке строка
пропускается (без нового анализа, запись в error_skipped_rows.txt и уведомление в
Telegram), worker берёт следующую. Если анализ не пришёл за 5 минут, восстановление
выполняется всё равно. Закрытая извне error-страница тоже больше не останавливает
worker. Правило добавлено в системные инструкции (OPERATOR_MISSION_1586, блок ERROR
SUPERVISOR) и в текст задания AUTO_ERROR_ASSIST. Запрет close/restart остаётся только
для SUCCESS_GUARD. Изменён tick_error_assist; обработчики подписи/страницы не тронуты.
'''

# Revision 4: autonomous SUCCESS/ERROR assist requests get a budget per page state.
# Before: every tick in SUCCESS_ASSIST re-queued a full developer-agent run every 45 s
# while the page did not change, and each run posted an identical report.
ASSIST_MARKER = "AUTO_ASSIST_BUDGET_1591R4"
RESIGNED_HANDLERS = {"queue_success_assist", "queue_error_assist", "tick_error_assist", "run_registration", "main",
                     "tick_post_auth_review", "tick_sign_wait",
                     "fill_test_signature",  # SIGN_QUADRANTS_1591R70: draws per quarter
                     "_agent_tools", "_agent_execute_tool",  # AGENT_MEMORY_1591R71: the signature tool
                     "tick_confirmation", "tick_resend"}  # CONFIRM_PUSH_1591R74: the cap is a setting
OLD_SUCCESS_THROTTLE = '''    now = monotonic()
    last = float(worker.get("success_ai_last_at") or 0)
    if not force and now - last < 45:
        return False

    worker["success_ai_last_at"] = now
    tab_id = int(worker.get("id") or 0)
'''
NEW_SUCCESS_THROTTLE = '''    if not _auto_assist_allowed(worker, "SUCCESS", force):
        return False
    tab_id = int(worker.get("id") or 0)
'''
OLD_ERROR_THROTTLE = '''    now = monotonic()
    last = float(worker.get("error_ai_last_at") or 0)
    if not force and now - last < 45:
        return False
    worker["error_ai_last_at"] = now

    tab_id = int(worker.get("id") or 0)
'''
NEW_ERROR_THROTTLE = '''    if not _auto_assist_allowed(worker, "ERROR", force):
        return False

    tab_id = int(worker.get("id") or 0)
'''
QUEUE_ERROR_DEF = "def queue_error_assist(worker, reason, force=False):\n"
ASSIST_HELPER = '''# AUTO_ASSIST_BUDGET_1591R4
AUTO_ASSIST_MIN_GAP_SECONDS = 45
AUTO_ASSIST_REPORTS_PER_STATE = 2
AUTO_ASSIST_REPEAT_SECONDS = 1800


def _auto_assist_pending(kind, tab_id):
    """True while an unanswered [AUTO_<kind>_ASSIST TAB n] job is still in the inbox."""
    conn = _ai_db_connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM inbox WHERE done_at IS NULL AND body LIKE ? LIMIT 1",
            (f"[AUTO_{kind}_ASSIST TAB {int(tab_id)}]%",),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _auto_assist_allowed(worker, kind, force=False):
    """Budget for autonomous assist requests: the page state, not the clock, decides.

    Per unchanged page URL at most AUTO_ASSIST_REPORTS_PER_STATE requests (the second
    one no sooner than AUTO_ASSIST_MIN_GAP_SECONDS after the first), then one every
    AUTO_ASSIST_REPEAT_SECONDS. A new URL starts a new budget. A request is never
    queued while the previous one for this tab has not been answered yet. `force`
    only waives the minimum gap.
    """
    now = monotonic()
    try:
        url = str(worker.get("page").url or "")
    except Exception:
        url = ""
    states = worker.setdefault("auto_assist_state", {})
    state = states.get(kind)
    if not state or state.get("url") != url:
        state = {"url": url, "count": 0, "last": 0.0}
        states[kind] = state
    try:
        if _auto_assist_pending(kind, worker.get("id") or 0):
            return False
    except Exception:
        pass
    since_last = now - float(state.get("last") or 0)
    if state["count"] >= AUTO_ASSIST_REPORTS_PER_STATE:
        if since_last < AUTO_ASSIST_REPEAT_SECONDS:
            return False
    elif state["count"] > 0 and not force and since_last < AUTO_ASSIST_MIN_GAP_SECONDS:
        return False
    state["count"] += 1
    state["last"] = now
    worker[f"{kind.lower()}_ai_last_at"] = now
    return True


'''
README_NOTE_R4 = '''

РЕВИЗИЯ 4 (fix_package_1591.py)
Бюджет автономных запросов SUCCESS_ASSIST/ERROR_ASSIST. Раньше каждый тик в фазе
SUCCESS_ASSIST ставил в очередь новый полный прогон агента каждые 45 секунд, пока
страница не менялась, и каждый прогон присылал одинаковый отчёт (8 одинаковых
сообщений за 8 минут, лишние токены). Теперь на одну неизменную страницу (URL)
не более двух запросов (второй не раньше чем через 45 с), затем один раз в 30 минут;
новый URL начинает новый бюджет; пока предыдущий запрос по этой вкладке не отвечен,
новый не ставится. Изменены только queue_success_assist и queue_error_assist;
обработчики страницы/подписи не тронуты. Маркер: AUTO_ASSIST_BUDGET_1591R4.
'''

# Revision 3: the proxy login is not embedded in the code any more. The runtime already
# prefers telegram_config.json "proxy" and the TELEGRAM_PROXY variable over this constant.
PROXY_LINE_RE = re.compile(r'^TELEGRAM_DEFAULT_PROXY = "(?:socks5h?|https?)://[^"\n]*"[ \t]*$', re.M)
NEW_PROXY_LINE = ('TELEGRAM_DEFAULT_PROXY = ""  # ' + PROXY_MARKER
                  + ': set "proxy" in telegram_config.json (or TELEGRAM_PROXY)')
OLD_MAIN_RECONSTRUCT = "    original, output = reconstruct(app, package)\n"
NEW_MAIN_RECONSTRUCT = ("    original, output = reconstruct(app, package)\n"
                        "    ensure_proxy_configured(app)\n")
PROXY_GUARD_SOURCE = '''

def ensure_proxy_configured(app):
    """r3: the code no longer embeds the Telegram proxy; it must be in telegram_config.json."""
    try:
        cfg = json.loads((app/'telegram_config.json').read_text('utf-8'))
    except (OSError, ValueError):
        cfg = {}
    proxy = str((cfg or {}).get('proxy') or '').strip()
    if proxy.lower() in ('direct', 'none', 'off', 'no', '-'):  # PROXY_DIRECT_1591R20: server outside RU, no proxy on purpose
        return
    if not proxy:
        raise RuntimeError('telegram_config.json has no "proxy". Add "proxy": "socks5h://user:password@host:port" '
                           '(the value that was TELEGRAM_DEFAULT_PROXY in the old code) before installing, '
                           'or "proxy": "direct" for a server outside Russia that reaches Telegram directly; '
                           'this build does not embed it and would otherwise reach Telegram without the proxy.')
'''

OLD_PUSH = '''            r, err = telegram_api(
                cfg,
                "sendMessage",
                {
                    "chat_id": chat,
                    "text": str(success_text)[:4000],
                    "disable_web_page_preview": "true",
                },
            )
            if not r:
                print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''
NEW_PUSH = '''            # SUCCESS_PUSH_DURABLE_1591R2: the whole text is queued and delivered in
            # confirmed parts by the durable sender; it is never cut to 4000 characters.
            success_text = str(success_text)
            if not success_text.strip():
                continue
            try:
                _io1591.enqueue_notice(globals(), chat, success_text)
                continue
            except Exception as exc:
                print(
                    "[Telegram] SUCCESS push не поставлен в очередь, отправляю напрямую: "
                    f"{_io1591.redact(exc)}",
                    flush=True,
                )
            for piece in _io1591.split_text(success_text):
                r, err = telegram_api(
                    cfg,
                    "sendMessage",
                    {
                        "chat_id": chat,
                        "text": piece,
                        "disable_web_page_preview": "true",
                    },
                )
                if not r:
                    print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''

# Version-independent structural hash: fields that are None or [] are omitted, which is
# what ast.dump() started doing by default in Python 3.13. Attributes are never included.
SIGNATURE_SOURCE = '''
def ast_signature(node):
    if isinstance(node, ast.AST):
        fields = []
        for name, value in ast.iter_fields(node):
            if value is None or (isinstance(value, list) and not value):
                continue
            fields.append((name, ast_signature(value)))
        return (type(node).__name__, tuple(fields))
    if isinstance(node, list):
        return tuple(ast_signature(x) for x in node)
    return repr(node)


def handler_hash(node):
    return hashlib.sha256(repr(ast_signature(node)).encode()).hexdigest()
'''
_ns: dict = {"ast": ast, "hashlib": hashlib}
exec(SIGNATURE_SOURCE, _ns)
ast_signature, handler_hash = _ns["ast_signature"], _ns["handler_hash"]

OLD_TEST_HASH = "            actual=hashlib.sha256(ast.dump(function(name),include_attributes=False).encode()).hexdigest()\n"
NEW_TEST_HASH = "            actual=handler_hash(function(name))\n"

OLD_INPUT_CHECK = '''        if digest(raw) != meta['input_sha256']:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
NEW_INPUT_CHECK = '''        accepted = {meta['input_sha256'], *meta.get('previous_output_sha256', [])}
        if digest(raw) not in accepted:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
OLD_RECONSTRUCT = '''        lines = raw.decode('utf-8').splitlines(keepends=True)
        for change in reversed(edits[name]):
            lines[change['start']:change['end']] = change['replacement']
        updated = ''.join(lines).encode('utf-8')
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: reconstruction checksum failed')
        result[name] = updated
'''
NEW_RECONSTRUCT = '''        # r2: the reviewed package copy is installed once the input checksum matched.
        updated = (package/name).read_bytes()
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: package copy checksum failed')
        result[name] = updated
'''

README_NOTE_R3 = '''

РЕВИЗИЯ 3 (fix_package_1591.py)
Логин и пароль прокси убраны из кода: TELEGRAM_DEFAULT_PROXY = "". Код и раньше
брал прокси сначала из telegram_config.json ("proxy"), затем из переменной
TELEGRAM_PROXY и только потом из константы. Перед установкой добавьте в
/opt/beeline/telegram_config.json ключ "proxy" со старым значением константы;
install.py отказывается продолжать, пока ключа нет. Маркер: PROXY_FROM_CONFIG_1591R3.
Значение из старого кода на сервере:  grep -o 'socks5h://[^"]*' /opt/beeline/test_beeline.py
'''

README_NOTE = '''

РЕВИЗИЯ 2 (fix_package_1591.py)
1. Отдельный SUCCESS push больше не обрезается до 4000 символов: текст целиком
   ставится в durable-очередь и доставляется частями с подтверждением; при
   недоступной очереди отправляется напрямую частями. Маркер в коде:
   SUCCESS_PUSH_DURABLE_1591R2. Редактируемые статусные сообщения (editMessageText)
   по-прежнему ограничены 4000 символами: часть edit-сообщения разделить нельзя.
2. Хэши защищённых обработчиков в test_update.py считаются по структуре AST без
   полей None/[] и не зависят от версии Python. Прежний ast.dump() давал другой
   текст на Python <= 3.12, из-за чего preflight установщика падал.
3. install.py ставит проверенные копии из пакета после совпадения входного хэша;
   edits.json сохранён как описание изменений. Сервер с уже установленной первой
   сборкой 15.91-io обновляется тем же путём.
Проверка после установки:
grep -c SUCCESS_PUSH_DURABLE_1591R2 /opt/beeline/test_beeline.py   # ожидается 1
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def node_range(source: str, node) -> tuple:
    """Character offsets of the whole lines a top-level node occupies."""
    lines = source.splitlines(keepends=True)
    return sum(map(len, lines[:node.lineno - 1])), sum(map(len, lines[:node.end_lineno]))


def only_function(source: str, name: str):
    nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise SystemExit(f"Expected one {name}; found {len(nodes)}. Source unchanged.")
    return nodes[0]


MAX_REVISION = int(os.environ.get("FIX_1591_MAX_REVISION") or 99)  # build an older revision on purpose
WITHOUT_R31 = os.environ.get("FIX_1591_WITHOUT_R31") == "1"  # r32 without the r31 signing code (lite build)


def replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{what}: expected exactly one occurrence, found {text.count(old)}; nothing changed")
    return text.replace(old, new, 1)


def add_edit(edits: list, output_before: str, old_block: str, new_block: str, reflected=None) -> None:
    """Record the new change in edits.json using the ORIGINAL (input) line numbers.

    `reflected` are the edits already applied in output_before (default: all of `edits`);
    edits appended during the same run are not part of output_before and must not shift
    lines. An earlier edit that lies completely inside old_block is absorbed: its effect
    is already part of old_block, so the new entry replaces it. Partial overlaps are refused.
    """
    reflected = edits if reflected is None else reflected
    out_lines = output_before.splitlines(keepends=True)
    old_lines = old_block.splitlines(keepends=True)
    starts = [i for i in range(len(out_lines)) if out_lines[i:i + len(old_lines)] == old_lines]
    if len(starts) != 1:
        raise SystemExit(f"edits.json: block not unique in the package output ({len(starts)} matches): {old_lines[0][:60]!r}")
    out_start = starts[0]
    out_end = out_start + len(old_lines)

    # A block that lies inside the replacement text of an earlier edit is a change to that
    # edit, not a new one: rewrite its replacement in place.
    delta = 0
    for change in sorted(reflected, key=lambda c: c["start"]):
        out_s = change["start"] + delta
        out_e = out_s + len(change["replacement"])
        if out_s <= out_start and out_end <= out_e:
            target = change.get("_orig") or next((c for c in edits if c is change), None)
            if target is None:
                raise SystemExit("edits.json: earlier edit not found; source unchanged")
            # The live entry, not the snapshot: a second change inside the same earlier edit during
            # an upgrade run must keep the first one (r44: three blocks of the r41 configurator entry).
            joined = "".join(target["replacement"])
            if joined.count(old_block) != 1:
                raise SystemExit("edits.json: block ambiguous inside an earlier edit; source unchanged")
            target["replacement"] = joined.replace(old_block, new_block, 1).splitlines(keepends=True)
            return
        delta += len(change["replacement"]) - (change["end"] - change["start"])

    def to_input(x):
        delta = 0
        for change in sorted(reflected, key=lambda c: c["start"]):
            shift = len(change["replacement"]) - (change["end"] - change["start"])
            out_s = change["start"] + delta
            out_e = out_s + len(change["replacement"])
            if out_e <= x:
                delta += shift
            elif out_s < x < out_e:
                raise SystemExit("edits.json: the new block cuts through an earlier edit; source unchanged")
        return x - delta

    in_start, in_end = to_input(out_start), to_input(out_end)
    absorbed = [c for c in reflected if in_start <= c["start"] and c["end"] <= in_end
                and c["start"] + 0 >= in_start]
    for a in absorbed:
        orig = a.get("_orig", a)
        if any(orig is c for c in edits):
            edits.remove(orig)
    edits.append({"start": in_start, "end": in_end, "replacement": new_block.splitlines(keepends=True)})
    edits.sort(key=lambda c: c["start"])


def revision_of(source: str) -> int:
    """Revision of a test_beeline.py that carries every marker up to r30."""
    if CONFIRM_TRACE_MARKER in source:
        return 76
    if ORDER_VERIFY_MARKER in source:
        return 75
    if CONFIRM_PUSH_MARKER in source:
        return 74
    if BASE_RESET_MARKER in source:
        return 73
    if REGION_CAPTION_MARKER in source:
        return 72
    if AGENT_MEMORY_MARKER in source:
        return 71
    if SIGN_QUADRANTS_MARKER in source:
        return 70
    if ORDER_REUSE_MARKER in source:
        return 69
    if TOKEN_REENTER_MARKER in source:
        return 68
    if REENTER_MARKER in source:
        return 67
    if AUTO_EXPIRE_MARKER in source:
        return 66
    if SETTING_RESTART_MARKER in source:
        return 65
    if BASE_TOOLS_MARKER in source:
        return 64
    if ESIM_ISSUED_MARKER in source:
        return 62
    if EXPORT_CARDS_MARKER in source:
        return 61
    if BOT_TOOLS_MARKER in source:
        return 60
    if LINK_STATUS_MARKER in source:
        return 59
    if LINK_CHECK_MARKER in source:
        return 58
    if QUIET_AUTO_MARKER in source:
        return 57
    if SHORT_REPORT_MARKER in source:
        return 56
    if SUCCESS_PAGE_MARKER in source:
        return 55
    if AUTO_TOOLS_MARKER in source:
        return 54
    if CONTACT_PHONE_MARKER in source:
        return 53
    if CLEAR_SAFE_MARKER in source:
        return 52   # the lite build (FIX_1591_WITHOUT_R31=1) is the same revision without the r31 signing code
    if PAYMENT_STRICT_MARKER in source:
        return 51
    if CLEAR_BASE_MARKER in source:
        return 50
    if EXHAUSTED_UNVERIFIED_MARKER in source:
        return 49
    if RESIGN_LIMIT_MARKER in source:
        return 48
    if STREET_RULE_MARKER in source:
        return 47
    if OPERATOR_LIVE_MARKER in source:
        return 46
    if CONFIGURATOR_SELECT_MARKER in source:
        return 45
    if CONFIGURATOR_DUMP_MARKER in source:
        return 44
    if BASKET_SUMMARY_MARKER in source:
        return 43
    if TARIFF_LOG_MARKER in source:
        return 42
    if TARIFF_CONFIG_MARKER in source:
        return 41
    if ISOLATED_CONTEXT_MARKER in source:
        return 40
    if SIGN_REJECTED_MARKER in source:
        return 39
    if TELEGRAM_MENU_MARKER in source:
        return 38
    if AI_SIGN_FAIL_MARKER in source:
        return 37
    if SIM_URL_MARKER in source:
        return 36
    if TRACE_COMPACT_MARKER in source:
        return 35
    if BROWSER_ENV_MARKER in source:
        return 34
    if TARIFF_CHANGE_MARKER in source:
        return 33
    if TARIFF_SCOPE_MARKER in source:
        return 32
    return 31 if SIGN_ROBUST_MARKER in source else 30


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    package = Path(argv[1]).resolve()
    app = package / "test_beeline.py"
    for name in ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "install.py",
                 "test_update.py", "manifest.json", "edits.json", "SHA256SUMS.txt", "README.txt"):
        if not (package / name).is_file():
            raise SystemExit(f"{package / name}: missing; this is not the extracted 15.91 package")
    source = app.read_text("utf-8")
    speed_file = package / "symbol_matching.py"
    speed_done = speed_file.is_file() and MATCHER_SPEED_MARKER in speed_file.read_text("utf-8")
    if speed_done and all(m in source for m in (MARKER, PROXY_MARKER, ASSIST_MARKER, ERROR_MARKER, OVERLAY_MARKER,
                                                TARIFF_MARKER, ROWSTART_MARKER, MATCHER_MARKER, OBSERVER_MARKER,
                                                PROFILE_MARKER, RESTART_MARKER, POSTAUTH_MARKER, PERSDATA_MARKER,
                                                ERRORSKIP_MARKER, SUCCESSTAG_MARKER, BROWSER_MARKER,
                                                PROFILE_LABELS_MARKER, PROXY_DIRECT_MARKER,
                                                RESTART_RELAUNCH_MARKER, ROW_SKIP_MARKER,
                                                FINAL_PAGE_MARKER, SIGNED_MARKER, SIGN_TRACE_MARKER,
                                                PAYMENT_MARKER, TG_RATE_MARKER, TWO_BROWSERS_MARKER,
                                                STALE_DRAIN_MARKER, AI_VERDICT_MARKER))\
            and (MAX_REVISION < 31 or WITHOUT_R31 or SIGN_ROBUST_MARKER in source)\
            and (MAX_REVISION < 32 or TARIFF_SCOPE_MARKER in source)\
            and (MAX_REVISION < 33 or TARIFF_CHANGE_MARKER in source)\
            and (MAX_REVISION < 34 or BROWSER_ENV_MARKER in source)\
            and (MAX_REVISION < 35 or TRACE_COMPACT_MARKER in source)\
            and (MAX_REVISION < 36 or SIM_URL_MARKER in source)\
            and (MAX_REVISION < 37 or AI_SIGN_FAIL_MARKER in source)\
            and (MAX_REVISION < 38 or TELEGRAM_MENU_MARKER in source)\
            and (MAX_REVISION < 39 or SIGN_REJECTED_MARKER in source)\
            and (MAX_REVISION < 40 or ISOLATED_CONTEXT_MARKER in source)\
            and (MAX_REVISION < 41 or TARIFF_CONFIG_MARKER in source)\
            and (MAX_REVISION < 42 or TARIFF_LOG_MARKER in source)\
            and (MAX_REVISION < 43 or BASKET_SUMMARY_MARKER in source)\
            and (MAX_REVISION < 44 or CONFIGURATOR_DUMP_MARKER in source)\
            and (MAX_REVISION < 45 or CONFIGURATOR_SELECT_MARKER in source)\
            and (MAX_REVISION < 46 or OPERATOR_LIVE_MARKER in source)\
            and (MAX_REVISION < 47 or STREET_RULE_MARKER in source)\
            and (MAX_REVISION < 48 or RESIGN_LIMIT_MARKER in source)\
            and (MAX_REVISION < 49 or EXHAUSTED_UNVERIFIED_MARKER in source)\
            and (MAX_REVISION < 50 or CLEAR_BASE_MARKER in source)\
            and (MAX_REVISION < 51 or PAYMENT_STRICT_MARKER in source)\
            and (MAX_REVISION < 52 or CLEAR_SAFE_MARKER in source)\
            and (MAX_REVISION < 53 or CONTACT_PHONE_MARKER in source)\
            and (MAX_REVISION < 54 or AUTO_TOOLS_MARKER in source)\
            and (MAX_REVISION < 55 or SUCCESS_PAGE_MARKER in source)\
            and (MAX_REVISION < 56 or SHORT_REPORT_MARKER in source)\
            and (MAX_REVISION < 57 or QUIET_AUTO_MARKER in source)\
            and (MAX_REVISION < 58 or LINK_CHECK_MARKER in source)\
            and (MAX_REVISION < 59 or LINK_STATUS_MARKER in source)\
            and (MAX_REVISION < 60 or BOT_TOOLS_MARKER in source)\
            and (MAX_REVISION < 61 or EXPORT_CARDS_MARKER in source)\
            and (MAX_REVISION < 62 or ESIM_ISSUED_MARKER in source)\
            and (MAX_REVISION < 64 or BASE_TOOLS_MARKER in source)\
            and (MAX_REVISION < 65 or SETTING_RESTART_MARKER in source)\
            and (MAX_REVISION < 66 or AUTO_EXPIRE_MARKER in source)\
            and (MAX_REVISION < 67 or REENTER_MARKER in source)\
            and (MAX_REVISION < 68 or TOKEN_REENTER_MARKER in source)\
            and (MAX_REVISION < 69 or ORDER_REUSE_MARKER in source)\
            and (MAX_REVISION < 70 or SIGN_QUADRANTS_MARKER in source)\
            and (MAX_REVISION < 71 or AGENT_MEMORY_MARKER in source)\
            and (MAX_REVISION < 72 or REGION_CAPTION_MARKER in source)\
            and (MAX_REVISION < 73 or BASE_RESET_MARKER in source)\
            and (MAX_REVISION < 74 or CONFIRM_PUSH_MARKER in source)\
            and (MAX_REVISION < 75 or ORDER_VERIFY_MARKER in source)\
            and (MAX_REVISION < 76 or CONFIRM_TRACE_MARKER in source)\
            and (not EXPERIMENT or EXPERIMENT_MARKER in source):
        print(f"Already revision {revision_of(source)}; nothing changed.")
        return 0
    if sha(app) not in ACCEPTED_PACKAGE_SHAS:
        raise SystemExit(f"test_beeline.py SHA256 {sha(app)} is not a reviewed 15.91-io build; nothing changed")
    manifest = json.loads((package / "manifest.json").read_text("utf-8"))
    edits = json.loads((package / "edits.json").read_text("utf-8"))
    # Edits already present in `source`, as snapshots (their replacement lengths must stay
    # those of `source`) linked to the live entries they describe.
    reflected = []
    for entry in edits["test_beeline.py"]:
        snapshot = dict(entry)
        snapshot["_orig"] = entry
        reflected.append(snapshot)
    new_source = source
    test_src = (package / "test_update.py").read_text("utf-8")
    install_src = (package / "install.py").read_text("utf-8")
    ctrl_source = (package / "server_controller.py").read_text("utf-8")
    ctrl_reflected = []
    for entry in edits["server_controller.py"]:
        snapshot = dict(entry)
        snapshot["_orig"] = entry
        ctrl_reflected.append(snapshot)
    new_ctrl = ctrl_source

    if MARKER not in source:
        # 1. SUCCESS push
        new_source = replace_once(new_source, OLD_PUSH, NEW_PUSH, "test_beeline.py SUCCESS push")
        add_edit(edits["test_beeline.py"], source, OLD_PUSH, NEW_PUSH, reflected)

        # 2. Version-independent handler hashes
        test_src = replace_once(test_src, OLD_TEST_HASH, NEW_TEST_HASH, "test_update.py hash line")
        test_src = replace_once(test_src, "\nclass SourceIntegrityTests(unittest.TestCase):\n",
                                "\n" + SIGNATURE_SOURCE + "\n\nclass SourceIntegrityTests(unittest.TestCase):\n",
                                "test_update.py SourceIntegrityTests")

        # 3. Installer uses the package copies
        install_src = replace_once(install_src, OLD_INPUT_CHECK, NEW_INPUT_CHECK, "install.py input check")
        install_src = replace_once(install_src, OLD_RECONSTRUCT, NEW_RECONSTRUCT, "install.py reconstruct")

    if PROXY_MARKER not in source:
        # 4 (r3). Proxy login out of the code; installer insists on telegram_config.json "proxy".
        matches = PROXY_LINE_RE.findall(new_source)
        if len(matches) != 1:
            raise SystemExit(f"TELEGRAM_DEFAULT_PROXY literal: expected one line, found {len(matches)}; nothing changed")
        old_proxy_line = PROXY_LINE_RE.search(new_source).group(0)
        new_source = new_source.replace(old_proxy_line, NEW_PROXY_LINE, 1)
        add_edit(edits["test_beeline.py"], source, old_proxy_line + "\n", NEW_PROXY_LINE + "\n", reflected)
        install_src = replace_once(install_src, OLD_MAIN_RECONSTRUCT, NEW_MAIN_RECONSTRUCT, "install.py main")
        install_src = replace_once(install_src, "\n\ndef main():\n", PROXY_GUARD_SOURCE + "\n\ndef main():\n",
                                   "install.py proxy guard")

    # 5 (r4). Budget for autonomous assist requests.
    if ASSIST_MARKER not in source:
        new_source = replace_once(new_source, OLD_SUCCESS_THROTTLE, NEW_SUCCESS_THROTTLE, "queue_success_assist throttle")
        new_source = replace_once(new_source, OLD_ERROR_THROTTLE, NEW_ERROR_THROTTLE, "queue_error_assist throttle")
        new_source = replace_once(new_source, QUEUE_ERROR_DEF, ASSIST_HELPER + QUEUE_ERROR_DEF, "assist helper insertion")
        add_edit(edits["test_beeline.py"], source, OLD_SUCCESS_THROTTLE, NEW_SUCCESS_THROTTLE, reflected)
        add_edit(edits["test_beeline.py"], source, OLD_ERROR_THROTTLE, NEW_ERROR_THROTTLE, reflected)
        add_edit(edits["test_beeline.py"], source, QUEUE_ERROR_DEF, ASSIST_HELPER + QUEUE_ERROR_DEF, reflected)
    # 6 (r5). registration/error: analyse, report, then close/reopen, retry once, skip.
    if ERROR_MARKER not in source:
        if ASSIST_MARKER not in new_source:
            raise SystemExit("revision 5 needs the revision 4 assist budget; nothing changed")
        # a) runtime: replace tick_error_assist and add the recovery helpers before it
        fn = only_function(new_source, "tick_error_assist")
        a, b = node_range(new_source, fn)
        old_tick = new_source[a:b]
        new_source = new_source[:a] + TICK_ERROR_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_tick, TICK_ERROR_R5, reflected)
        # b) AUTO_ERROR_ASSIST task text
        fn = only_function(new_source, "queue_error_assist")
        assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "text" for t in n.targets)]
        if len(assigns) != 1:
            raise SystemExit("queue_error_assist: text assignment not unambiguous")
        a, b = node_range(new_source, assigns[0])
        old_text = new_source[a:b]
        new_source = new_source[:a] + QUEUE_ERROR_TEXT_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_text, QUEUE_ERROR_TEXT_R5, reflected)
        # c) ERROR SUPERVISOR block of the agent system prompt
        a = new_source.index("ERROR SUPERVISOR:\n")
        b = new_source.index("Правила действий:\n", a)
        old_block = new_source[a:b]
        new_source = new_source[:a] + AGENT_ERROR_BLOCK_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_block, AGENT_ERROR_BLOCK_R5, reflected)
        # d) the priority mission constant
        missions = [n for n in ast.parse(new_source).body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "OPERATOR_MISSION_1586" for t in n.targets)]
        if len(missions) != 1:
            raise SystemExit("OPERATOR_MISSION_1586 not unambiguous")
        a, b = node_range(new_source, missions[0])
        old_mission = new_source[a:b]
        if not old_mission.rstrip("\n").endswith('"""'):
            raise SystemExit("OPERATOR_MISSION_1586 is not a triple-quoted literal")
        new_mission = old_mission.rstrip("\n")[:-3] + MISSION_RULE_R5 + '"""\n'
        new_source = new_source[:a] + new_mission + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_mission, new_mission, reflected)

    # 7 (r6). Portal modal over the basket: dismiss it, click through it, longer CDP close.
    if OVERLAY_MARKER not in source:
        anchor = "def esim_state(page):\n"
        new_source = replace_once(new_source, anchor, OVERLAY_HELPER_R6 + anchor, "esim_state anchor")
        add_edit(edits["test_beeline.py"], source, anchor, OVERLAY_HELPER_R6 + anchor, reflected)
        for old, new, what in ((OLD_SELECT_ESIM_ATTEMPT, NEW_SELECT_ESIM_ATTEMPT, "select_esim attempt"),
                               (OLD_TARIFF_CLICK, NEW_TARIFF_CLICK, "click_tariff_change loop"),
                               (OLD_CHOOSE_LOOP, NEW_CHOOSE_LOOP, "second choose loop")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        # CDP close: the original body becomes the nested _once(); the same top-level name
        # gains a 20 s timeout and one retry. Tests that extract the function by name still work.
        fn = only_function(new_source, "_close_cdp_page_for_worker")
        a, b = node_range(new_source, fn)
        old_fn = new_source[a:b]
        if not old_fn.startswith(OLD_CDP_DEF):
            raise SystemExit("_close_cdp_page_for_worker signature differs; source unchanged")
        nested = "".join(("    " + line if line.strip() else line) for line in old_fn.splitlines(keepends=True))
        nested = nested.replace("    " + OLD_CDP_DEF, "    def _once(cdp_url, info, timeout=20):\n", 1)
        new_fn = CDP_HEAD_R6 + nested + CDP_TAIL_R6
        new_source = new_source[:a] + new_fn + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_fn, new_fn, reflected)

    # 8 (r7). Tariff card by name; the overlay dismisser protects the dialog we need.
    if TARIFF_MARKER not in source:
        for old, new, what in ((OVERLAY_HELPER_R6, OVERLAY_HELPER_R7, "overlay helper"),
                               (OLD_CHOOSE_LOOP_R6, NEW_CHOOSE_LOOP_R7, "choose loop by name"),
                               (OLD_ESIM_DISMISS_R6, NEW_ESIM_DISMISS_R7, "esim dismiss keep")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                # Built from a pre-r6 package in this run: fold r7 into the r6 entry just recorded.
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: r6 entry for {what} not found")

    # 9 (r8). Activity-aware ROW_START watchdog; heartbeat from long steps; retry in place.
    if ROWSTART_MARKER not in source:
        anchor = "def esim_state(page):\n"
        for old, new, what in ((anchor, ROW_PROGRESS_HELPER_R8 + anchor, "row progress helper"),
                               (OLD_WATCHDOG_ROW_START, NEW_WATCHDOG_ROW_START, "watchdog ROW_START"),
                               (OLD_TARIFF_OPEN, NEW_TARIFF_OPEN, "tariff open progress"),
                               (OLD_TARIFF_RETRY, NEW_TARIFF_RETRY, "tariff retry in place"),
                               (OLD_CHOOSE_PRINT, NEW_CHOOSE_PRINT, "choose progress"),
                               (OLD_ESIM_CALL, NEW_ESIM_CALL, "esim progress")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 10 (r9). CPU-based matcher liveness in the parent; the 75 s rule is untouched.
    if MATCHER_MARKER not in source:
        anchor = "def parent_watchdog(processes, heartbeat):\n"
        for old, new, what in ((anchor, MATCHER_HELPER_R9 + anchor, "matcher helper"),
                               (OLD_WATCHDOG_MATCHER, NEW_WATCHDOG_MATCHER, "watchdog matcher branch"),
                               (OLD_HEALTH_MATCHER, NEW_HEALTH_MATCHER, "host worker health")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 11 (r10). Faster matcher: symbol_matching.py 14.1 joins the package; the installer
    # replaces the server's 14.0 copy (checksum-verified) and imports the new module.
    if not speed_done:
        if not SYMBOL_MATCHING_SOURCE.is_file():
            raise SystemExit(f"{SYMBOL_MATCHING_SOURCE}: missing; nothing changed")
        speed_source = SYMBOL_MATCHING_SOURCE.read_text("utf-8")
        if MATCHER_SPEED_MARKER not in speed_source or "MATCHER_VERSION = '14.1'" not in speed_source:
            raise SystemExit("matcher_r10/symbol_matching.py is not the revision 10 matcher; nothing changed")
        compile(speed_source, "symbol_matching.py", "exec")
        speed_file.write_text(speed_source, "utf-8")
        manifest["files"]["symbol_matching.py"] = {
            "input_sha256": SYMBOL_MATCHING_INPUT_SHA,
            "output_sha256": hashlib.sha256(speed_source.encode("utf-8")).hexdigest(),
            "previous_output_sha256": [],
        }
        for old, new, what in ((OLD_INSTALL_FILES, NEW_INSTALL_FILES, "install.py FILES"),
                               (OLD_INSTALL_LOOP, NEW_INSTALL_LOOP, "install.py reconstruct loop"),
                               (OLD_INSTALL_IMPORT, NEW_INSTALL_IMPORT, "install.py import check"),
                               (OLD_INSTALL_ASSERT, NEW_INSTALL_ASSERT, "install.py version assert")):
            install_src = replace_once(install_src, old, new, what)
        test_src = replace_once(test_src, OLD_TEST_COMPILE_LIST, NEW_TEST_COMPILE_LIST, "test_update.py compile list")
        test_src = replace_once(test_src, OLD_TEST_FIXTURE, NEW_TEST_FIXTURE, "test_update.py installer fixture")

    # 12 (r11). Bounded page collection in the DeepSeek lanes; busy ceiling in the supervisor.
    if OBSERVER_MARKER not in source:
        for old, new, what in ((OLD_COLLECT_DEF, OBSERVER_HELPER_R11 + NEW_COLLECT_DEF, "observer collect wrapper"),
                               (OLD_LANE_STALE, NEW_LANE_STALE, "lane busy ceiling")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 13 (r12). Text capture of the contract screen for the SUCCESS profile.
    if PROFILE_MARKER not in source:
        new_source = replace_once(new_source, OLD_CAPTURE_WRAPPER, PROFILE_TEXT_HELPER_R12 + NEW_CAPTURE_WRAPPER,
                                  "contract capture wrapper")
        add_edit(edits["test_beeline.py"], source, OLD_CAPTURE_WRAPPER, PROFILE_TEXT_HELPER_R12 + NEW_CAPTURE_WRAPPER,
                 reflected)

    # 14 (r13). Scheduled graceful restart: runtime drain + controller command and relaunch.
    if RESTART_MARKER not in source:
        anchor = "def parent_watchdog(processes, heartbeat):\n"
        for old, new, what in ((anchor, RESTART_HELPER_R13 + anchor, "restart helpers"),
                               (OLD_WORKER_GATE, NEW_WORKER_GATE, "worker restart gate"),
                               (OLD_DEAD_SKIP, NEW_DEAD_SKIP, "dead recovery skip"),
                               (OLD_CASCADE_HEAD, NEW_CASCADE_HEAD, "restart timer"),
                               (OLD_FINAL_LOOP, NEW_FINAL_LOOP, "no replacement while draining"),
                               (OLD_QUEUE_DONE, NEW_QUEUE_DONE, "restart exit")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        for old, new, what in ((OLD_CTRL_CLASS, NEW_CTRL_CLASS, "controller restart helpers"),
                               (OLD_CTRL_SLASH, NEW_CTRL_SLASH, "controller /restart"),
                               (OLD_CTRL_LOOP, NEW_CTRL_LOOP, "controller relaunch")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
        test_src = replace_once(test_src, OLD_TEST_CTRL_NS, NEW_TEST_CTRL_NS, "test_update.py controller fixture")

    # 15 (r14). /registration/error in the post-auth review follows the error policy.
    if POSTAUTH_MARKER not in source:
        new_source = replace_once(new_source, OLD_POST_AUTH_ERROR, NEW_POST_AUTH_ERROR, "post-auth error route")
        add_edit(edits["test_beeline.py"], source, OLD_POST_AUTH_ERROR, NEW_POST_AUTH_ERROR, reflected)

    # 16 (r15). Deterministic operator refusal: skip the row without analysis or retry.
    if PERSDATA_MARKER not in source:
        new_source = replace_once(new_source, OLD_ENTER_ERROR_GUARD, NEW_ENTER_ERROR_GUARD, "enter_error_guard")
        add_edit(edits["test_beeline.py"], source, OLD_ENTER_ERROR_GUARD, NEW_ENTER_ERROR_GUARD, reflected)

    # 17 (r16). Every registration error: replace the tab and skip the row, no DeepSeek.
    if ERRORSKIP_MARKER not in source:
        for old, new, what in ((OLD_GUARD_HEAD_R15, NEW_GUARD_HEAD_R16, "enter_error_guard head r16"),
                               (OLD_GUARD_TAIL, NEW_GUARD_TAIL_R16, "enter_error_guard tail r16"),
                               (OLD_MISSION_R5_TEXT, NEW_MISSION_R16_TEXT, "mission rule r16"),
                               (OLD_AGENT_BLOCK_R5, NEW_AGENT_BLOCK_R16, "agent error block r16"),
                               (OLD_QUEUE_SENTENCE_R5, NEW_QUEUE_SENTENCE_R16, "queue_error_assist text r16")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 18 (r17). #успешно on the SUCCESS push; four tabs per Chromium.
    if SUCCESSTAG_MARKER not in source:
        for old, new, what in ((OLD_SUCCESS_HEAD, NEW_SUCCESS_HEAD, "success message tag"),
                               (OLD_TABS_LINE, NEW_TABS_LINE, "four tabs")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 19 (r18). Whole-browser restart when Chromium stops answering CDP; real "\n" in the status.
    if BROWSER_MARKER not in source:
        for old, new, what in ((OLD_WAIT_CDP, OLD_WAIT_CDP + BROWSER_HELPERS_R18, "browser hang helpers"),
                               (OLD_CDP_CONNECT_R6, NEW_CDP_CONNECT_R18, "cdp connect note"),
                               (OLD_CDP_EXCEPT_R6, NEW_CDP_EXCEPT_R18, "cdp except note"),
                               (OLD_EXPERIMENT_LINE, NEW_EXPERIMENT_LINE, "startup banner"),
                               (OLD_DEAD_HEAD, NEW_DEAD_HEAD, "restart_browser_instance"),
                               (OLD_CLOSE_FAIL, NEW_CLOSE_FAIL, "watchdog browser hang trigger"),
                               (OLD_STATUS_NL, NEW_STATUS_NL, "watchdog status line break")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 20 (r19). Profile fields on the personal-data form that carry no label of their own.
    if PROFILE_LABELS_MARKER not in source:
        for old, new, what in ((OLD_FINAL_CAPTURE_DEF, NEW_FINAL_CAPTURE_DEF, "profile label helpers"),
                               (OLD_ALIASES_HEAD, NEW_ALIASES_HEAD, "profile aliases head"),
                               (OLD_ALIASES_ADDRESS, NEW_ALIASES_ADDRESS, "profile aliases address"),
                               (OLD_MATCH_LOOP, NEW_MATCH_LOOP, "profile match loop")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        test_src = replace_once(test_src, OLD_TEST_PROFILE_NS, NEW_TEST_PROFILE_NS, "test_update.py profile fixture")

    # 21 (r20). "proxy": "direct" — a server outside Russia talks to Telegram without a proxy.
    if PROXY_DIRECT_MARKER not in source:
        for old, new, what in ((OLD_PROXY_FN_DEF, NEW_PROXY_FN_DEF, "direct proxy values"),
                               (OLD_PROXY_EMPTY_CHECK, NEW_PROXY_EMPTY_CHECK, "direct proxy check")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 22 (r21). Relaunch after the drain by marker, not only by the exit code xvfb-run may lose.
    if RESTART_RELAUNCH_MARKER not in source:
        for old, new, what in ((OLD_CLEAR_DRAIN_R13, NEW_CLEAR_DRAIN_R21, "relaunch helper"),
                               (OLD_DRAIN_EXIT_R13, NEW_DRAIN_EXIT_R21, "drain exit marker"),
                               (OLD_BROWSER_EXIT_R18, NEW_BROWSER_EXIT_R21, "browser exit marker")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        for old, new, what in ((OLD_CTRL_RELAUNCH_R13, NEW_CTRL_RELAUNCH_R21, "controller relaunch by marker"),
                               (OLD_CTRL_REAP, NEW_CTRL_REAP_R21, "controller reap"),
                               (OLD_CTRL_INIT, NEW_CTRL_INIT_R21, "controller last_code")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            if old in ctrl_source:
                add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
            else:
                for change in edits["server_controller.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 23 (r22). INVALID_ROW retried once in a fresh tab; skipped rows recorded as processed.
    if ROW_SKIP_MARKER not in source:
        for old, new, what in ((OLD_RESET_STATE_DEF, NEW_RESET_STATE_DEF, "invalid row helpers"),
                               (OLD_FINISH_HEAD, NEW_FINISH_HEAD_R22, "finish_worker_row invalid row"),
                               (OLD_R5_SKIP_TAIL, NEW_R5_SKIP_TAIL_R22, "r5 skip remembers the row"),
                               (OLD_R15_SKIP_TAIL, NEW_R15_SKIP_TAIL_R22, "r15 skip remembers the row")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 24 (r23). Final (contract) page URL and document links in the success record and push.
    if FINAL_PAGE_MARKER not in source:
        for old, new, what in ((OLD_DIAG_KEEP, NEW_DIAG_KEEP, "diagnostic sessions to keep"),
                               (OLD_WRITE_SUCCESS_HEAD, NEW_WRITE_SUCCESS_HEAD, "final page helpers"),
                               (OLD_REC_PROFILE, NEW_REC_PROFILE, "success record final page"),
                               (OLD_SUCCESS_TAIL, NEW_SUCCESS_TAIL, "success message final page")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 25 (r24). Success needs positive evidence of the signed contract; otherwise UNVERIFIED.
    if SIGNED_MARKER not in source:
        for old, new, what in ((OLD_SIGN_WAIT_DEF, NEW_SIGN_WAIT_DEF, "signed evidence helpers"),
                               (OLD_SIGN_WAIT_FINAL, NEW_SIGN_WAIT_FINAL, "sign wait settle"),
                               (OLD_REVIEW_FINAL, NEW_REVIEW_FINAL, "post-auth review settle")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 26 (r25). Trace of the server's answers around the «Подписать договор» click.
    if SIGN_TRACE_MARKER not in source:
        for old, new, what in ((OLD_SIGN_WAIT_DEF_R24, NEW_SIGN_WAIT_DEF_R25, "sign trace helpers"),
                               (OLD_SIGN_CALL_R14, NEW_SIGN_CALL_R25, "sign call trace"),
                               (OLD_UNVERIFIED_REC_R24, NEW_UNVERIFIED_REC_R25, "unverified record trace"),
                               (OLD_UNVERIFIED_MSG_R24, NEW_UNVERIFIED_MSG_R25, "unverified message trace"),
                               (OLD_SUCCESS_REC_R23, NEW_SUCCESS_REC_R25, "success record trace"),
                               (OLD_MATCH_SKIP_R19, NEW_MATCH_SKIP_R25, "profile junk values")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 27 (r26). The payment step after the signature is its own outcome, not a success.
    if PAYMENT_MARKER not in source:
        for old, new, what in ((OLD_SETTLE_DEF_R24, NEW_SETTLE_DEF_R26, "payment helpers"),
                               (OLD_SETTLE_HEAD_R24, NEW_SETTLE_HEAD_R26, "settle payment check")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 28 (r27). Telegram status logger within the Bot API limits; messages reused across restarts.
    if TG_RATE_MARKER not in source:
        for old, new, what in ((OLD_LOGGER_DEF, NEW_LOGGER_DEF, "tg rate helpers"),
                               (OLD_LOGGER_STATE, NEW_LOGGER_STATE, "logger state"),
                               (OLD_LOGGER_CREATE, NEW_LOGGER_CREATE, "logger message reuse"),
                               (OLD_LOGGER_EDIT, NEW_LOGGER_EDIT, "logger rate-limited edits")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 29 (r28). Two Chromium instances; captchas of different tabs do not pile up.
    if TWO_BROWSERS_MARKER not in source:
        for old, new, what in ((OLD_BROWSER_COUNT, NEW_BROWSER_COUNT, "two browsers + captcha gate"),
                               (OLD_TAB_PROCESS_DEF, NEW_TAB_PROCESS_DEF, "tab process captcha gate arg"),
                               (OLD_CONFIGURE_MATCHER, NEW_CONFIGURE_MATCHER, "tab process captcha gate set"),
                               (OLD_PROCESSES_INIT, NEW_PROCESSES_INIT, "captcha gate semaphore"),
                               (OLD_SPAWN_KWARGS, NEW_SPAWN_KWARGS, "spawn captcha gate")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 30 (r29). A drain file left by a killed run is discarded at start.
    if STALE_DRAIN_MARKER not in source:
        old, new, what = OLD_RESTART_TIMER_R13, NEW_RESTART_TIMER_R29, "stale drain reset"
        new_source = replace_once(new_source, old, new, what)
        for change in edits["test_beeline.py"]:
            joined = "".join(change["replacement"])
            if old in joined:
                change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                break
        else:
            raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 31 (r30). DeepSeek's mandate and VERDICT line (prompt only; the code part is r31).
    if AI_VERDICT_MARKER not in source:
        for old, new, what in ((OLD_ASSIST_TAIL, NEW_ASSIST_TAIL_R30, "assist mandate"),
                               (OLD_MISSION_BULLET, NEW_MISSION_BULLET_R30, "mission verdict")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 32 (r31). Deterministic signing, DeepSeek/runtime coordination, the verdict read by the code.
    if SIGN_ROBUST_MARKER not in source and MAX_REVISION >= 31 and not WITHOUT_R31:
        for old, new, what in ((OLD_POST_AUTH_DEF, NEW_POST_AUTH_DEF, "sign robust helpers"),
                               (OLD_BUTTON_BLOCK, NEW_BUTTON_BLOCK_R30, "yield to deepseek"),
                               *(((OLD_SIGN_CALL_R25, NEW_SIGN_CALL_R30, "sign prepare + retry"),)
                                 if OLD_SIGN_CALL_R25 in new_source else
                                 ((OLD_SIGN_CALL_R25_WITH_R48, NEW_SIGN_CALL_R30_WITH_R48, "sign prepare + retry (lite upgrade, r48)"),)),
                               (OLD_OBSERVER_PRINT, NEW_OBSERVER_PRINT, "observer busy flag"),
                               (OLD_OBSERVER_COMPLETE, NEW_OBSERVER_COMPLETE, "observer verdict"),
                               (OLD_OBSERVER_FAIL, NEW_OBSERVER_FAIL, "observer busy off"),
                               *(((OLD_SETTLE_PAYMENT_R26, NEW_SETTLE_PAYMENT_R30, "settle verdict"),)
                                 if OLD_SETTLE_PAYMENT_R26 in new_source else
                                 ((OLD_SETTLE_PAYMENT_R26_WITH_R37, NEW_SETTLE_PAYMENT_R30_WITH_R37, "settle verdict (lite upgrade)"),)
                                 if OLD_SETTLE_PAYMENT_R26_WITH_R37 in new_source else
                                 ((OLD_SETTLE_PAYMENT_R26_WITH_R49, NEW_SETTLE_PAYMENT_R30_WITH_R49, "settle verdict (lite upgrade, r49)"),))):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if OLD_TEST_OBSERVER_NS in test_src:
            test_src = replace_once(test_src, OLD_TEST_OBSERVER_NS, NEW_TEST_OBSERVER_NS, "test_update.py observer fixture")
        else:  # RESIGN_LIMIT_1591R48 already put its switch before '_ai_db_fail' (lite → full upgrade)
            test_src = replace_once(test_src, OLD_TEST_OBSERVER_NS.replace("            '_ai_db_fail'", "            'AI_ENABLED_1591R48':True,'_ai_db_fail'"),
                                    NEW_TEST_OBSERVER_NS.replace("            '_ai_db_fail'", "            'AI_ENABLED_1591R48':True,'_ai_db_fail'"),
                                    "test_update.py observer fixture (after r48)")

    # 33 (r32). Tariff card inside the picker, same-row restart cap, drain deadline.
    if TARIFF_SCOPE_MARKER not in source and MAX_REVISION >= 32:
        for old, new, what in ((OLD_TARIFF_FINDER_R32, NEW_TARIFF_FINDER_R32, "tariff card in picker"),
                               (OLD_ROW_READY_R32, NEW_ROW_READY_R32, "same-row restart cap"),
                               (OLD_RESET_DEF_R32, NEW_RESET_DEF_R32, "row restart helpers"),
                               (OLD_DRAIN_TICK_R32, NEW_DRAIN_TICK_R32, "drain deadline tick"),
                               (OLD_LOAD_PROCESSED_R32, NEW_LOAD_PROCESSED_R32, "drain deadline helpers"),
                               (OLD_DEAD_SPAWN_R32, NEW_DEAD_SPAWN_R32, "respawn cap (dead recovery)"),
                               (OLD_STALL_SPAWN_R32, NEW_STALL_SPAWN_R32, "respawn cap (watchdog)")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 34 (r33). The tariff «изменить», not the region one.
    if TARIFF_CHANGE_MARKER not in source and MAX_REVISION >= 33:
        for old, new, what in ((OLD_TARIFF_CHANGE_R33, NEW_TARIFF_CHANGE_R33, "tariff change button"),
                               (OLD_TARIFF_HELPER_ANCHOR_R33, NEW_TARIFF_HELPER_R33, "tariff change helper")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 35 (r34). BROWSER_COUNT from BEELINE_BROWSERS.
    if BROWSER_ENV_MARKER not in source and MAX_REVISION >= 34:
        old, new, what = OLD_BROWSER_COUNT_R34, NEW_BROWSER_COUNT_R34, "browser count from env"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 36 (r35). Compact sign trace in Telegram.
    if TRACE_COMPACT_MARKER not in source and MAX_REVISION >= 35:
        old, new, what = OLD_TRACE_LINES_R35, NEW_TRACE_LINES_R35, "compact sign trace"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 37 (r36). The pushed order link is the current row's.
    if SIM_URL_MARKER not in source and MAX_REVISION >= 36:
        for old, new, what in ((OLD_PENDING_URL_R36, NEW_PENDING_URL_R36, "offer url per row"),
                               (OLD_RESET_STATE_R36, NEW_RESET_STATE_R36, "reset offer memory")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        # /res <номер eSIM | строка>: the controller answers with the row's real order link.
        for old, new, what in ((OLD_CTRL_IMPORT_R36, NEW_CTRL_IMPORT_R36, "controller import re"),
                               (OLD_CTRL_RESTART_BRANCH_R36, NEW_CTRL_RESTART_BRANCH_R36, "controller /res branch"),
                               (OLD_CTRL_RELAUNCH_DEF_R36, NEW_CTRL_ROWLINK_R36, "controller /res command")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            if old in ctrl_source:
                add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
            else:
                for change in edits["server_controller.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier controller entry for {what} not found")
        test_src = replace_once(test_src, OLD_TEST_CTRL_NS_R36, NEW_TEST_CTRL_NS_R36, "test_update.py controller fixture (/res)")

    # 38 (r37). DeepSeek only when the signature did not go through.
    if AI_SIGN_FAIL_MARKER not in source and MAX_REVISION >= 37:
        for old, new, what in ((OLD_GUARD_DEF_R37, NEW_GUARD_DEF_R37, "sign went through helper"),
                               (OLD_GUARD_ASSIST_R37, NEW_GUARD_ASSIST_R37, "no assist at guard entry"),
                               (OLD_AFTER_CLICK_R37, NEW_AFTER_CLICK_R37, "assist only when unsent"),
                               (OLD_SIGN_ERROR_R37, NEW_SIGN_ERROR_R37, "error after sign: unverified, no assist"),
                               (OLD_EVIDENCE_R37, NEW_EVIDENCE_R37, "network acceptance as evidence")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 39 (r38). The inline menu: module, controller routing, installer, status snapshot, short pushes.
    if TELEGRAM_MENU_MARKER not in source and MAX_REVISION >= 38:
        if not TELEGRAM_MENU_SOURCE.is_file():
            raise SystemExit(f"{TELEGRAM_MENU_SOURCE}: missing; nothing changed")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 38 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }
        for old, new, what in ((OLD_STATUS_SYNC_R38, NEW_STATUS_SYNC_R38, "status snapshot"),
                               (OLD_LOGGER_START_R38, NEW_LOGGER_START_R38, "logger without status messages"),
                               (OLD_SUCCESS_MSG_R38, NEW_SUCCESS_MSG_R38, "short success push"),
                               (OLD_PAYMENT_MSG_R38, NEW_PAYMENT_MSG_R38, "short payment push"),
                               (OLD_REC_TIME_R38, NEW_REC_TIME_R38, "success record time")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        for old, new, what in ((OLD_C_IMPORT_R38, NEW_C_IMPORT_R38, "controller menu import"),
                               (OLD_C_MARKUP_R38, NEW_C_MARKUP_R38, "controller keyboard removed"),
                               (OLD_C_PROC_R38, NEW_C_PROC_R38, "controller menu object"),
                               (OLD_C_HELLO_R38, NEW_C_HELLO_R38, "controller greeting"),
                               (OLD_C_LOOP_R38, NEW_C_LOOP_R38, "controller menu tick"),
                               (OLD_C_ALLOWED_R38, NEW_C_ALLOWED_R38, "controller callback updates"),
                               (OLD_C_MSG_R38, NEW_C_MSG_R38, "controller callback routing"),
                               (OLD_C_START_R38, NEW_C_START_R38, "controller /start"),
                               (OLD_C_UNKNOWN_R38, NEW_C_UNKNOWN_R38, "controller unknown command"),
                               (OLD_C_AI_R38, NEW_C_AI_R38, "controller ai gate")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            if old in ctrl_source:
                add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
            else:
                for change in edits["server_controller.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier controller entry for {what} not found")
        for old, new, what in ((OLD_I_FILES_R38, NEW_I_FILES_R38, "install.py FILES (menu)"),
                               (OLD_I_SUPPORT_R38, NEW_I_SUPPORT_R38, "install.py menu module"),
                               (OLD_I_IMPORT_R38, NEW_I_IMPORT_R38, "install.py import (menu)"),
                               (OLD_I_ASSERT_R38, NEW_I_ASSERT_R38, "install.py version assert (menu)")):
            install_src = replace_once(install_src, old, new, what)
        for old, new, what in ((OLD_T_FIX_R38, NEW_T_FIX_R38, "test_update.py installer fixture (menu)"),
                               (OLD_T_CTRL_R38, NEW_T_CTRL_R38, "test_update.py controller fixture (menu)"),
                               (OLD_T_COMPILE_R38, NEW_T_COMPILE_R38, "test_update.py compile list (menu)")):
            test_src = replace_once(test_src, old, new, what)

    # 40 (r39). A site refusal after the click is a rejection; tabs per Chromium from the environment.
    if SIGN_REJECTED_MARKER not in source and MAX_REVISION >= 39:
        for old, new, what in ((OLD_WENT_R39, NEW_WENT_R39, "strict acceptance + rejection helper"),
                               (OLD_SETTLE_HEAD_R39, NEW_SETTLE_HEAD_R39, "settle: rejection first"),
                               (OLD_AFTER_R39, NEW_AFTER_R39, "after click: rejection"),
                               (OLD_ERR_R39, NEW_ERR_R39, "error page: rejection code"),
                               (OLD_TABS_R39, NEW_TABS_R39, "tabs per browser from env")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 41 (r40). An own browser context per worker tab.
    if ISOLATED_CONTEXT_MARKER not in source and MAX_REVISION >= 40:
        for old, new, what in ((OLD_TAB_DEF_R40, NEW_TAB_DEF_R40, "isolated context helper"),
                               (OLD_TAB_CONTEXT_R40, NEW_TAB_CONTEXT_R40, "worker uses its own context")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        test_src = replace_once(test_src, OLD_TEST_TAB_NS_R40, NEW_TEST_TAB_NS_R40, "test_update.py _tab_process fixture (context)")

    # 42 (r41). The tariff from the environment; a configurator after the card is confirmed.
    if TARIFF_CONFIG_MARKER not in source and MAX_REVISION >= 41:
        for old, new, what in ((OLD_TARIFF_NAME_R41, NEW_TARIFF_NAME_R41, "tariff from env"),
                               (OLD_CHOOSE_BREAK_R41, NEW_CHOOSE_BREAK_R41, "configurator confirm call"),
                               (OLD_CARD_DEF_R41, NEW_CARD_DEF_R41, "configurator confirm helper"),
                               (OLD_CARD_RULE_R41, NEW_CARD_RULE_R41, "card rule: one choose button"),
                               (OLD_CHANGE_TITLES_R41, NEW_CHANGE_TITLES_R41, "change button near any tariff name")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 43 (r42). The journal names the configured tariff instead of the literal bee START.
    if TARIFF_LOG_MARKER not in source and MAX_REVISION >= 42:
        for old, new, what in ((OLD_TARIFF_SEEN_R42, NEW_TARIFF_SEEN_R42, "tariff seen message"),
                               (OLD_TARIFF_WAIT_R42, NEW_TARIFF_WAIT_R42, "tariff wait message"),
                               (OLD_TARIFF_START_R42, NEW_TARIFF_START_R42, "tariff at startup")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 44 (r43). The basket summary: journal, diagnostic, records and the push.
    if BASKET_SUMMARY_MARKER not in source and MAX_REVISION >= 43:
        for old, new, what in ((OLD_BASKET_CALL_R43, NEW_BASKET_CALL_R43, "basket summary call"),
                               (OLD_BASKET_DEF_R43, NEW_BASKET_DEF_R43, "basket summary helper"),
                               (OLD_BASKET_SUCCESS_R43, NEW_BASKET_SUCCESS_R43, "basket in the success record"),
                               (OLD_BASKET_PAYMENT_R43, NEW_BASKET_PAYMENT_R43, "basket in the payment record"),
                               (OLD_BASKET_UNVERIFIED_R43, NEW_BASKET_UNVERIFIED_R43, "basket in the unverified record"),
                               (OLD_BASKET_PUSH_R43, NEW_BASKET_PUSH_R43, "basket line of the push")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 45 (r44). Prices from the tariff's card; the configurator dumped before it is confirmed.
    if CONFIGURATOR_DUMP_MARKER not in source and MAX_REVISION >= 44:
        for old, new, what in ((OLD_BASKET_DEF_HEAD_R44, NEW_BASKET_DEF_HEAD_R44, "basket/configurator JS"),
                               (OLD_BASKET_EVAL_R44, NEW_BASKET_EVAL_R44, "basket: card prices"),
                               (OLD_BASKET_PRINT_R44, NEW_BASKET_PRINT_R44, "basket: journal line"),
                               (OLD_BASKET_DIAG_R44, NEW_BASKET_DIAG_R44, "basket: page text in the diagnostic"),
                               (OLD_CONFIG_DEF_R44, NEW_CONFIG_DEF_R44, "configurator dump helper"),
                               (OLD_CONFIG_SCOPE_R44, NEW_CONFIG_SCOPE_R44, "configurator: remember the dialog"),
                               (OLD_CONFIG_PRINT_R44, NEW_CONFIG_PRINT_R44, "configurator: dump before confirming"),
                               (OLD_STRICT_CALL_R44, NEW_STRICT_CALL_R44, "basket: require the tariff"),
                               (OLD_STRICT_DEF_R44, NEW_STRICT_DEF_R44, "basket: strict helper"),
                               (OLD_CONFIG_RE_R44, NEW_CONFIG_RE_R44, "configurator: header/prefix regexes"),
                               (OLD_CONFIG_SECOND_R44, NEW_CONFIG_SECOND_R44, "configurator: panel recognised by its text")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 46 (r45). The configurator panel decides; the minimal set and the price check before «выбрать».
    if CONFIGURATOR_SELECT_MARKER not in source and MAX_REVISION >= 45:
        for old, new, what in ((OLD_CFG_CONDITION_R45, NEW_CFG_CONDITION_R45, "configurator: handled whenever visible"),
                               (OLD_CFG_CONFIRM_R45, NEW_CFG_CONFIRM_R45, "configurator: minimal set before confirming"),
                               (OLD_CFG_DEFS_R45, NEW_CFG_DEFS_R45, "configurator: selection helpers"),
                               (OLD_BASKET_SUMMARY_LINE_R45, NEW_BASKET_SUMMARY_LINE_R45, "basket: tariff block"),
                               (OLD_BASKET_PRINT_LINE_R45, NEW_BASKET_PRINT_LINE_R45, "basket: tariff block in the journal"),
                               (OLD_STRICT_SEEN_R45, NEW_STRICT_SEEN_R45, "basket: tariff block in the strict message")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 47 (r46). A menu question is an operator order; wider command words; one dump line; monthly price first.
    if OPERATOR_LIVE_MARKER not in source and MAX_REVISION >= 46:
        for old, new, what in ((OLD_LIVE_WORDS_R46, NEW_LIVE_WORDS_R46, "operator: command words"),
                               (OLD_DUMP_HEAD_R46, NEW_DUMP_HEAD_R46, "configurator dump: announce flag"),
                               (OLD_DUMP_PRINT_R46, NEW_DUMP_PRINT_R46, "configurator dump: print once"),
                               (OLD_AFTER_DUMP_R46, NEW_AFTER_DUMP_R46, "configurator: quiet second read"),
                               (OLD_BARE_R46, NEW_BARE_R46, "configurator: monthly price first")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if OPERATOR_LIVE_MARKER not in ctrl_source:
            for old, new, what in ((OLD_C_ASK_R46, NEW_C_ASK_R46, "controller: menu question as /op"),):
                new_ctrl = replace_once(new_ctrl, old, new, what)
                if old in ctrl_source:
                    add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
                else:
                    for change in edits["server_controller.py"]:
                        joined = "".join(change["replacement"])
                        if old in joined:
                            change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                            break
                    else:
                        raise SystemExit(f"edits.json: earlier controller entry for {what} not found")

    # 48 (r47). The street rule in the auto job and the mission.
    if STREET_RULE_MARKER not in source and MAX_REVISION >= 47:
        for old, new, what in ((OLD_AUTO_CITY_R47, NEW_AUTO_CITY_R47, "street rule: auto job"),
                               (OLD_MISSION_CITY_R47, NEW_MISSION_CITY_R47, "street rule: mission")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 49 (r48). Two sign clicks per row at most; the observer's page budget grows with the tabs.
    if RESIGN_LIMIT_MARKER not in source and MAX_REVISION >= 48:
        for old, new, what in ((OLD_OBSERVER_LIMIT_R48, NEW_OBSERVER_LIMIT_R48, "observer: budget per tab"),
                               (OLD_AI_GATE_DEF_R48, NEW_AI_GATE_DEF_R48, "ai switch: constant"),
                               (OLD_AI_GATE_BODY_R48, NEW_AI_GATE_BODY_R48, "ai switch: no automatic jobs"),
                               (OLD_AI_LANE_R48, NEW_AI_LANE_R48, "ai switch: idle lanes"),
                               (OLD_AI_START_R48, NEW_AI_START_R48, "ai switch: startup line")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if "RESIGN_LIMIT_1591R48" not in ctrl_source:
            # The /op block of r46 lies inside the AI-gate entry of r38 in edits.json: rewrite the entry
            # that carries it instead of mapping positions.
            new_ctrl = replace_once(new_ctrl, OLD_C_AI_OFF_R48, NEW_C_AI_OFF_R48, "controller: DeepSeek off answer")
            for change in edits["server_controller.py"]:
                joined = "".join(change["replacement"])
                if OLD_C_AI_OFF_R48 in joined:
                    change["replacement"] = joined.replace(OLD_C_AI_OFF_R48, NEW_C_AI_OFF_R48, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit("edits.json: earlier controller entry for the /op block not found")
        if "AI_ENABLED_1591R48" not in test_src:
            test_src = replace_once(test_src, OLD_TEST_AI_NS_R48, NEW_TEST_AI_NS_R48, "test_update.py observer fixture (ai switch)")

    # 50 (r49). An exhausted row is never a success by the network alone; the hold status names DeepSeek only when on.
    if EXHAUSTED_UNVERIFIED_MARKER not in source and MAX_REVISION >= 49:
        for old, new, what in ((OLD_HOLD_STATUS_R49, NEW_HOLD_STATUS_R49, "hold status: DeepSeek named only when on"),):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 51 (r50). /clear: the current base out of the queue.
    if CLEAR_BASE_MARKER not in source and MAX_REVISION >= 50:
        for old, new, what in ((OLD_CLEAR_MARK_R50, NEW_CLEAR_MARK_R50, "clear: marker"),):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if CLEAR_BASE_MARKER not in ctrl_source:
            for old, new, what in ((OLD_C_CLEAR_DEF_R50, NEW_C_CLEAR_DEF_R50, "controller: /clear helper"),
                                   (OLD_C_CLEAR_CMD_R50, NEW_C_CLEAR_CMD_R50, "controller: /clear command")):
                new_ctrl = replace_once(new_ctrl, old, new, what)
                if old in ctrl_source:
                    add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
                else:
                    for change in edits["server_controller.py"]:
                        joined = "".join(change["replacement"])
                        if old in joined:
                            change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                            break
                    else:
                        raise SystemExit(f"edits.json: earlier controller entry for {what} not found")

    # 52 (r51). The payment step only by its heading; a registration-method page is never payment.
    if PAYMENT_STRICT_MARKER not in source and MAX_REVISION >= 51:
        for old, new, what in ((OLD_PAYMENT_LOW_R51, NEW_PAYMENT_LOW_R51, "payment: strict screen"),):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 53 (r52). The /clear check tolerates a message without text.
    if CLEAR_SAFE_MARKER not in source and MAX_REVISION >= 52:
        for old, new, what in ((OLD_CLEAR_SAFE_MARK_R52, NEW_CLEAR_SAFE_MARK_R52, "clear safe: marker"),):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if CLEAR_SAFE_MARKER not in ctrl_source:
            new_ctrl = replace_once(new_ctrl, OLD_C_CLEAR_SAFE_R52, NEW_C_CLEAR_SAFE_R52, "controller: /clear with an empty text")
            for change in edits["server_controller.py"]:
                joined = "".join(change["replacement"])
                if OLD_C_CLEAR_SAFE_R52 in joined:
                    change["replacement"] = joined.replace(OLD_C_CLEAR_SAFE_R52, NEW_C_CLEAR_SAFE_R52, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit("edits.json: earlier controller entry for /clear not found")

    # 54 (r53). Current and legacy contact phone forms use one strict locator.
    if CONTACT_PHONE_MARKER not in source and MAX_REVISION >= 53:
        anchor = 'def run_registration(page, diagnostic, phone, digits, active_digits, second_value, form_ready=False, launch_ready_event=None):\n'
        replacements = (
            (anchor, CONTACT_PHONE_SOURCE_R53 + anchor),
            ('        field = page.get_by_placeholder("+7 999 999 99")\n',
             '        field = _contact_phone_field(page)\n'),
            ('            contact = page.get_by_placeholder("+7 999 999 99")\n',
             '            contact = _contact_phone_field(page)\n'),
        )
        for old, new in replacements:
            new_source = replace_once(new_source, old, new, "contact phone locator")
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = replace_once(joined, old, new, "contact phone edit").splitlines(keepends=True)
                        break
                else:
                    raise SystemExit("edits.json: contact phone entry not found")

    # 55 (r54). An auto job is never a code change request: it gets the live tool set.
    if AUTO_TOOLS_MARKER not in source and MAX_REVISION >= 54:
        for old, new, what in ((OLD_CODE_REQ_R54, NEW_CODE_REQ_R54, "auto jobs: live tools"),):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 56 (r55). The success page: region by caption, stale auto jobs closed at start, statuses with DeepSeek off.
    if SUCCESS_PAGE_MARKER not in source and MAX_REVISION >= 55:
        for old, new, what in ((OLD_REGION_CAND_R55, NEW_REGION_CAND_R55, "success page: region by caption"),
                               (OLD_STALE_DEF_R55, NEW_STALE_DEF_R55, "success page: stale auto jobs helper"),
                               (OLD_STALE_CALL_R55, NEW_STALE_CALL_R55, "success page: stale auto jobs at start"),
                               *((o, n, "success page: status with DeepSeek off") for o, n in AI_STATUS_R55),
                               *((o, n, "success page: no browser restart over a signing tab") for o, n in GUARD_BROWSER_R55)):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 57 (r56). No DeepSeek reports: one short line instead.
    if SHORT_REPORT_MARKER not in source and MAX_REVISION >= 56:
        pairs = []
        for old_block, new_block in SHORT_REPORT_LINES_R56:
            # line by line: a single line never cuts through an earlier edit of edits.json
            old_lines = old_block.splitlines(keepends=True)
            pairs.append((old_lines[0], new_block))
            pairs.extend((line, "") for line in old_lines[1:])
        for old_sent, new_sent in SHORT_REPORT_SENTENCES_R56:
            lines = [l for l in new_source.splitlines(keepends=True) if old_sent in l]
            if len(lines) != 1:
                raise SystemExit(f"short report: {len(lines)} lines carry {old_sent[:40]!r}")
            pairs.append((lines[0], lines[0].replace(old_sent, new_sent, 1)))
        for old, new in pairs:
            what = "short report: " + old.strip()[:40]
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 58 (r57). DeepSeek quiet in the normal flow: grace before three triggers, outdated jobs skipped, «-» not sent.
    if QUIET_AUTO_MARKER not in source and MAX_REVISION >= 57:
        pairs = list(QUIET_PAIRS_R57)
        for old_sent, new_sent in QUIET_SENTENCES_R57:
            lines = [l for l in new_source.splitlines(keepends=True) if old_sent in l]
            if len(lines) != 1:
                raise SystemExit(f"quiet auto: {len(lines)} lines carry {old_sent[:40]!r}")
            pairs.append((lines[0], lines[0].replace(old_sent, new_sent, 1)))
        for old, new in pairs:
            what = "quiet auto: " + old.strip()[:40]
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if "_auto_job_outdated_1591r57" not in test_src:
            test_src = replace_once(test_src, OLD_TEST_QUIET_NS_R57, NEW_TEST_QUIET_NS_R57, "test_update.py observer fixture (quiet auto)")
        # MENU_DELETE_1591R57: the menu module ships again (🗑 delete from «Мои eSIM», new eSIMs today).
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if "MENU_DELETE_1591R57" not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 57 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 59 (r58). Link check and safe delete in the menu: the runtime carries the marker, the menu ships.
    if LINK_CHECK_MARKER not in source and MAX_REVISION >= 58:
        old, new, what = OLD_LINK_MARK_R58, NEW_LINK_MARK_R58, "link check: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if LINK_CHECK_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 58 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 60 (r59). The link check: errorCode NONE is no error, DOCS_GENERATED waits for the payment.
    if LINK_STATUS_MARKER not in source and MAX_REVISION >= 59:
        old, new, what = OLD_LINK_STATUS_MARK_R59, NEW_LINK_STATUS_MARK_R59, "link status: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if LINK_STATUS_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 59 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 61 (r60). The bot's tools in the menu: marker, two controller hooks, the menu module ships.
    if BOT_TOOLS_MARKER not in source and MAX_REVISION >= 60:
        old, new, what = OLD_BOT_TOOLS_MARK_R60, NEW_BOT_TOOLS_MARK_R60, "bot tools: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if BOT_TOOLS_MARKER not in ctrl_source:
            for old, new, what in ((OLD_C_MENU_START_R60, NEW_C_MENU_START_R60, "controller: menu.on_start"),
                                   (OLD_C_MENU_TEXT_R60, NEW_C_MENU_TEXT_R60, "controller: menu.handle_text")):
                new_ctrl = replace_once(new_ctrl, old, new, what)
                if old in ctrl_source:
                    add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
                else:
                    for change in edits["server_controller.py"]:
                        joined = "".join(change["replacement"])
                        if old in joined:
                            change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                            break
                    else:
                        raise SystemExit(f"edits.json: earlier controller entry for {what} not found")
        if "handle_text=lambda t:False" not in test_src:
            test_src = replace_once(test_src, OLD_TEST_MENU_NS_R60, NEW_TEST_MENU_NS_R60, "test_update.py controller fixture (menu hooks)")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if BOT_TOOLS_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 60 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 62 (r61). The menu only: «Мои eSIM» as in r59 with the status icons, export refresh as the export.
    if EXPORT_CARDS_MARKER not in source and MAX_REVISION >= 61:
        old, new, what = OLD_EXPORT_CARDS_MARK_R61, NEW_EXPORT_CARDS_MARK_R61, "export cards: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if EXPORT_CARDS_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 61 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 63 (r62). The menu only: ESIM_SUCCESS is an issued eSIM (✅), not a dead link.
    if ESIM_ISSUED_MARKER not in source and MAX_REVISION >= 62:
        old, new, what = OLD_ESIM_ISSUED_MARK_R62, NEW_ESIM_ISSUED_MARK_R62, "esim issued: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if ESIM_ISSUED_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 62 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 65 (r64; r63 was published by hand). «📂 База» filter and append, «🔢 Генерация»: marker, controller, menu.
    if BASE_TOOLS_MARKER not in source and MAX_REVISION >= 64:
        old, new, what = OLD_BASE_TOOLS_MARK_R64, NEW_BASE_TOOLS_MARK_R64, "base tools: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if BASE_TOOLS_MARKER not in ctrl_source:
            for old, new, what in ((OLD_C_PENDING_R64, NEW_C_PENDING_R64, "controller: append pending file"),
                                   (OLD_C_FILTER_R64, NEW_C_FILTER_R64, "controller: upload filter"),
                                   (OLD_C_LOOP_R64, NEW_C_LOOP_R64, "controller: added rows after the queue"),
                                   (OLD_C_CALLBACK_R64, NEW_C_CALLBACK_R64, "controller: base menu modes"),
                                   *((o, n, "controller: button clears the append") for o, n in C_BUTTONS_R64),
                                   (OLD_C_ASK_R64, NEW_C_ASK_R64, "controller: upload hint"),
                                   (OLD_C_UPLOAD_R64, NEW_C_UPLOAD_R64, "controller: filtered upload")):
                new_ctrl = replace_once(new_ctrl, old, new, what)
                if old in ctrl_source:
                    add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
                else:
                    for change in edits["server_controller.py"]:
                        joined = "".join(change["replacement"])
                        if old in joined:
                            change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                            break
                    else:
                        raise SystemExit(f"edits.json: earlier controller entry for {what} not found")
        if "'_continue_appended_base':" not in test_src:
            test_src = replace_once(test_src, OLD_TEST_CONTINUE_R64, NEW_TEST_CONTINUE_R64, "test_update.py controller fixture (append)")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if BASE_TOOLS_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 64 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 66 (r65). The menu only: a setting restarts the bot once, from tick().
    if SETTING_RESTART_MARKER not in source and MAX_REVISION >= 65:
        old, new, what = OLD_SETTING_RESTART_MARK_R65, NEW_SETTING_RESTART_MARK_R65, "setting restart: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if SETTING_RESTART_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 65 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 67 (r66). The menu only: eSIMs older than 5 days leave «Мои eSIM».
    if AUTO_EXPIRE_MARKER not in source and MAX_REVISION >= 66:
        old, new, what = OLD_AUTO_EXPIRE_MARK_R66, NEW_AUTO_EXPIRE_MARK_R66, "auto expire: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if AUTO_EXPIRE_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 66 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 68 (r67). Re-enter the row on «введите данные снова», no «Подписать» loop, the steps page is not payment.
    if REENTER_MARKER not in source and MAX_REVISION >= 67:
        for old, new, what in ((OLD_REENTER_MARK_R67, NEW_REENTER_MARK_R67, "reenter: marker"),
                               (OLD_REENTER_HEAD_R67, NEW_REENTER_HEAD_R67, "reenter: helpers"),
                               (OLD_REENTER_CALL_R67, NEW_REENTER_CALL_R67, "reenter: enter_error_guard"),
                               (OLD_SIGN_CALL_R67, NEW_SIGN_CALL_R67, "sign throttle: the sign block"),
                               (OLD_SIGN_STEPS_R67, NEW_SIGN_STEPS_R67, "sign steps: DeepSeek prompt")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 69 (r68). 412 PERSONAL_TOKEN_ERROR after the signature re-enters the row instead of ❔.
    if TOKEN_REENTER_MARKER not in source and MAX_REVISION >= 68:
        for old, new, what in ((OLD_TOKEN_MARK_R68, NEW_TOKEN_MARK_R68, "token reenter: marker"),
                               (OLD_TOKEN_DEF_R68, NEW_TOKEN_DEF_R68, "token reenter: forced reason"),
                               (OLD_TOKEN_HINT_R68, NEW_TOKEN_HINT_R68, "token reenter: hint"),
                               (OLD_TOKEN_FINISH_R68, NEW_TOKEN_FINISH_R68, "token reenter: before ❔")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 70 (r69). Order link reuse, grey rows in the same form, corporate rows, mobile proxy, strict base filter.
    if ORDER_REUSE_MARKER not in source and MAX_REVISION >= 69:
        for old, new, what in ORDER_EDITS_R69:
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        if BASE_STRICT_MARKER not in ctrl_source:
            for old, new, what in C_EDITS_R69:
                new_ctrl = replace_once(new_ctrl, old, new, what)
                if old in ctrl_source:
                    add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
                else:
                    for change in edits["server_controller.py"]:
                        joined = "".join(change["replacement"])
                        if old in joined:
                            change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                            break
                    else:
                        raise SystemExit(f"edits.json: earlier controller entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if "MOBILE_PROXY_1591R69" not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 69 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 71 (r70). The signature drawn per quarter and checked; an empty one redrawn; the tab kept, DeepSeek instead of ❔.
    if SIGN_QUADRANTS_MARKER not in source and MAX_REVISION >= 70:
        for old, new, what in SIGNQ_EDITS_R70:
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 72 (r71). DeepSeek remembers the dialogue and draws the signature; a row resumes its confirmation attempt.
    if AGENT_MEMORY_MARKER not in source and MAX_REVISION >= 71:
        for old, new, what in MEM_EDITS_R71:
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 73 (r72). «укажите область» filled at once, DeepSeek after 8 s, up to 6 re-entries, an honest log line.
    if REGION_CAPTION_MARKER not in source and MAX_REVISION >= 72:
        for old, new, what in REG_EDITS_R72:
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 74 (r73). The menu only: «Сбросить прогресс» in «📂 База», the export count in the settings.
    if BASE_RESET_MARKER not in source and MAX_REVISION >= 73:
        old, new, what = OLD_RESET_MARK_R73, NEW_RESET_MARK_R73, "base reset: marker"
        new_source = replace_once(new_source, old, new, what)
        if old in source:
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        else:
            for change in edits["test_beeline.py"]:
                joined = "".join(change["replacement"])
                if old in joined:
                    change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                    break
            else:
                raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if BASE_RESET_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 73 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 75 (r74). Push requests on the confirmation page are a setting (menu «📲 Push», BEELINE_CONFIRM_ATTEMPTS).
    if CONFIRM_PUSH_MARKER not in source and MAX_REVISION >= 74:
        for old, new, what in PUSH_EDITS_R74:
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if CONFIRM_PUSH_MARKER not in menu_source or 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 74 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }

    # 76 (r75). A row is not written off by the look of /registration/error: the order is read by its own link first.
    if ORDER_VERIFY_MARKER not in source and MAX_REVISION >= 75:
        for old, new, what in VERIFY_EDITS_R75:
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 77 (r76). The site's answers before an error page on the confirmation screen are kept (confirm_errors.jsonl).
    if CONFIRM_TRACE_MARKER not in source and MAX_REVISION >= 76:
        for old, new, what in TRACE_EDITS_R76:
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # Experiment browsers8 (a separate build): the Chromium cap 4 → 8 and a startup line.
    if EXPERIMENT == "browsers8" and EXPERIMENT_MARKER not in source:
        for old, new, what in ((OLD_BROWSER_CAP_EXP, NEW_BROWSER_CAP_EXP, "experiment: browser cap 8"),
                               (OLD_START_LINE_EXP, NEW_START_LINE_EXP, "experiment: startup line")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    if EXPERIMENT == "browsers8" and OLD_EXP_AI_DEFAULT in new_source:
        # DeepSeek off by default in the experiment build; also when an older exp build is upgraded
        # (the marker is already there, the r48 constant is new).
        new_source = replace_once(new_source, OLD_EXP_AI_DEFAULT, NEW_EXP_AI_DEFAULT, "experiment: DeepSeek off by default")
        for change in edits["test_beeline.py"]:
            joined = "".join(change["replacement"])
            if OLD_EXP_AI_DEFAULT in joined:
                change["replacement"] = joined.replace(OLD_EXP_AI_DEFAULT, NEW_EXP_AI_DEFAULT, 1).splitlines(keepends=True)
                break
        else:
            raise SystemExit("edits.json: earlier entry for the AI default not found")

    built_revision = revision_of(new_source)
    compile(new_source, "test_beeline.py", "exec")
    compile(new_ctrl, "server_controller.py", "exec")
    compile(test_src, "test_update.py", "exec")
    compile(install_src, "install.py", "exec")

    # 4. Manifest and checksums
    tree = ast.parse(new_source)
    for name in manifest["preserved_handlers"]:
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1:
            raise SystemExit(f"preserved handler {name}: found {len(nodes)}")
        manifest["preserved_ast_sha256"][name] = handler_hash(nodes[0])
    old_hashes = {n: handler_hash(next(x for x in ast.parse(source).body
                                        if isinstance(x, ast.FunctionDef) and x.name == n))
                  for n in manifest["preserved_handlers"]}
    changed = {n for n in old_hashes if old_hashes[n] != manifest["preserved_ast_sha256"][n]}
    if changed - RESIGNED_HANDLERS:
        raise SystemExit(f"Preserved handlers changed unexpectedly: {sorted(changed - RESIGNED_HANDLERS)}")
    # A server that already runs the first 15.91 build is upgraded in place as well.
    manifest["files"]["test_beeline.py"]["previous_output_sha256"] = sorted(ACCEPTED_PACKAGE_SHAS)
    manifest["files"]["test_beeline.py"]["output_sha256"] = hashlib.sha256(new_source.encode("utf-8")).hexdigest()
    ctrl_meta = manifest["files"]["server_controller.py"]
    previous_ctrl = set(ctrl_meta.get("previous_output_sha256", [])) | CONTROLLER_ACCEPTED_SHAS
    ctrl_meta["previous_output_sha256"] = sorted(previous_ctrl)
    ctrl_meta["output_sha256"] = hashlib.sha256(new_ctrl.encode("utf-8")).hexdigest()
    manifest["revision"] = built_revision
    if EXPERIMENT:
        manifest["experiment"] = EXPERIMENT

    app.write_text(new_source, "utf-8")
    (package / "server_controller.py").write_text(new_ctrl, "utf-8")
    (package / "test_update.py").write_text(test_src, "utf-8")
    (package / "install.py").write_text(install_src, "utf-8")
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    (package / "edits.json").write_text(json.dumps(edits, ensure_ascii=False, indent=2), "utf-8")
    readme = package / "README.txt"
    for heading, note in (("РЕВИЗИЯ 2", README_NOTE), ("РЕВИЗИЯ 3", README_NOTE_R3), ("РЕВИЗИЯ 4", README_NOTE_R4),
                          ("РЕВИЗИЯ 5", README_NOTE_R5), ("РЕВИЗИЯ 6", README_NOTE_R6),
                          ("РЕВИЗИЯ 7", README_NOTE_R7), ("РЕВИЗИЯ 8", README_NOTE_R8),
                          ("РЕВИЗИЯ 9", README_NOTE_R9), ("РЕВИЗИЯ 10", README_NOTE_R10),
                          ("РЕВИЗИЯ 11", README_NOTE_R11), ("РЕВИЗИЯ 12", README_NOTE_R12),
                          ("РЕВИЗИЯ 13", README_NOTE_R13), ("РЕВИЗИЯ 14", README_NOTE_R14),
                          ("РЕВИЗИЯ 15", README_NOTE_R15), ("РЕВИЗИЯ 16", README_NOTE_R16),
                          ("РЕВИЗИЯ 17", README_NOTE_R17), ("РЕВИЗИЯ 18", README_NOTE_R18),
                          ("РЕВИЗИЯ 19", README_NOTE_R19),
                          ("РЕВИЗИЯ 20", README_NOTE_R20),
                          ("РЕВИЗИЯ 21", README_NOTE_R21),
                          ("РЕВИЗИЯ 22", README_NOTE_R22),
                          ("РЕВИЗИЯ 23", README_NOTE_R23),
                          ("РЕВИЗИЯ 24", README_NOTE_R24),
                          ("РЕВИЗИЯ 25", README_NOTE_R25),
                          ("РЕВИЗИЯ 26", README_NOTE_R26),
                          ("РЕВИЗИЯ 27", README_NOTE_R27),
                          ("РЕВИЗИЯ 28", README_NOTE_R28),
                          ("РЕВИЗИЯ 29", README_NOTE_R29),
                          ("РЕВИЗИЯ 30", README_NOTE_R30),
                          *((("РЕВИЗИЯ 31", README_NOTE_R31),) if SIGN_ROBUST_MARKER in new_source else ()),
                          *((("РЕВИЗИЯ 32", README_NOTE_R32),) if built_revision >= 32 else ()),
                          *((("РЕВИЗИЯ 33", README_NOTE_R33),) if built_revision >= 33 else ()),
                          *((("РЕВИЗИЯ 34", README_NOTE_R34),) if built_revision >= 34 else ()),
                          *((("РЕВИЗИЯ 35", README_NOTE_R35),) if built_revision >= 35 else ()),
                          *((("РЕВИЗИЯ 36", README_NOTE_R36),) if built_revision >= 36 else ()),
                          *((("РЕВИЗИЯ 37", README_NOTE_R37),) if built_revision >= 37 else ()),
                          *((("РЕВИЗИЯ 38", README_NOTE_R38),) if built_revision >= 38 else ()),
                          *((("РЕВИЗИЯ 39", README_NOTE_R39),) if built_revision >= 39 else ()),
                          *((("РЕВИЗИЯ 40", README_NOTE_R40),) if built_revision >= 40 else ()),
                          *((("РЕВИЗИЯ 41", README_NOTE_R41),) if built_revision >= 41 else ()),
                          *((("РЕВИЗИЯ 42", README_NOTE_R42),) if built_revision >= 42 else ()),
                          *((("РЕВИЗИЯ 43", README_NOTE_R43),) if built_revision >= 43 else ()),
                          *((("РЕВИЗИЯ 44", README_NOTE_R44),) if built_revision >= 44 else ()),
                          *((("РЕВИЗИЯ 45", README_NOTE_R45),) if built_revision >= 45 else ()),
                          *((("РЕВИЗИЯ 46", README_NOTE_R46),) if built_revision >= 46 else ()),
                          *((("РЕВИЗИЯ 47", README_NOTE_R47),) if built_revision >= 47 else ()),
                          *((("РЕВИЗИЯ 48", README_NOTE_R48),) if built_revision >= 48 else ()),
                          *((("РЕВИЗИЯ 49", README_NOTE_R49),) if built_revision >= 49 else ()),
                          *((("РЕВИЗИЯ 50", README_NOTE_R50),) if built_revision >= 50 else ()),
                          *((("РЕВИЗИЯ 51", README_NOTE_R51),) if built_revision >= 51 else ()),
                          *((("РЕВИЗИЯ 52", README_NOTE_R52),) if built_revision >= 52 else ()),
                          *((("РЕВИЗИЯ 53", README_NOTE_R53),) if built_revision >= 53 else ()),
                          *((("РЕВИЗИЯ 54", README_NOTE_R54),) if built_revision >= 54 else ()),
                          *((("РЕВИЗИЯ 55", README_NOTE_R55),) if built_revision >= 55 else ()),
                          *((("РЕВИЗИЯ 56", README_NOTE_R56),) if built_revision >= 56 else ()),
                          *((("РЕВИЗИЯ 57", README_NOTE_R57),) if built_revision >= 57 else ()),
                          *((("РЕВИЗИЯ 58", README_NOTE_R58),) if built_revision >= 58 else ()),
                          *((("РЕВИЗИЯ 59", README_NOTE_R59),) if built_revision >= 59 else ()),
                          *((("РЕВИЗИЯ 60", README_NOTE_R60),) if built_revision >= 60 else ()),
                          *((("РЕВИЗИЯ 61", README_NOTE_R61),) if built_revision >= 61 else ()),
                          *((("РЕВИЗИЯ 62", README_NOTE_R62),) if built_revision >= 62 else ()),
                          *((("РЕВИЗИЯ 64", README_NOTE_R64),) if built_revision >= 64 else ()),
                          *((("РЕВИЗИЯ 65", README_NOTE_R65),) if built_revision >= 65 else ()),
                          *((("РЕВИЗИЯ 66", README_NOTE_R66),) if built_revision >= 66 else ()),
                          *((("РЕВИЗИЯ 67", README_NOTE_R67),) if built_revision >= 67 else ()),
                          *((("РЕВИЗИЯ 68", README_NOTE_R68),) if built_revision >= 68 else ()),
                          *((("РЕВИЗИЯ 69", README_NOTE_R69),) if built_revision >= 69 else ()),
                          *((("РЕВИЗИЯ 70", README_NOTE_R70),) if built_revision >= 70 else ()),
                          *((("РЕВИЗИЯ 71", README_NOTE_R71),) if built_revision >= 71 else ()),
                          *((("РЕВИЗИЯ 72", README_NOTE_R72),) if built_revision >= 72 else ()),
                          *((("РЕВИЗИЯ 73", README_NOTE_R73),) if built_revision >= 73 else ()),
                          *((("РЕВИЗИЯ 74", README_NOTE_R74),) if built_revision >= 74 else ()),
                          *((("РЕВИЗИЯ 75", README_NOTE_R75),) if built_revision >= 75 else ()),
                          *((("РЕВИЗИЯ 76", README_NOTE_R76),) if built_revision >= 76 else ()),
                          *((("ЭКСПЕРИМЕНТ browsers8", README_NOTE_EXP),) if EXPERIMENT == "browsers8" else ())):
        if heading not in readme.read_text("utf-8"):
            readme.write_text(readme.read_text("utf-8").rstrip("\n") + note, "utf-8")

    # Prove the package's own suite passes here, then record it.
    run = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_update"], cwd=package,
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    (package / "test_results.txt").write_text(run.stdout, "utf-8")
    if run.returncode:
        print(run.stdout)
        raise SystemExit("Package tests failed after the fix; review test_results.txt")
    ran = next((line for line in run.stdout.splitlines() if line.startswith("Ran ")), "")
    verification = json.loads((package / "verification.json").read_text("utf-8"))
    verification.update({"python": sys.version, "revision": built_revision, "result": "OK",
                         "tests": int(ran.split()[1]) if ran else None,
                         "exact_input_sha256": manifest["files"]})
    (package / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), "utf-8")

    sums = [f"{sha(package / name)}  {name}" for name in
            ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "symbol_matching.py", "telegram_menu.py",
             "install.py", "test_update.py", "manifest.json", "edits.json", "README.txt", "verification.json",
             "test_results.txt", "install_preflight_results.txt") if (package / name).is_file()]
    (package / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", "utf-8")
    for line in ("__pycache__",):
        for cache in package.glob(line):
            for f in cache.iterdir():
                f.unlink()
            cache.rmdir()
    print(ran + " — OK")
    print(f"Revision {built_revision} applied to", package, f"(experiment {EXPERIMENT})" if EXPERIMENT else "")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
