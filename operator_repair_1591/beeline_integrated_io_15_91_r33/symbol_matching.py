"""Pure local image matching. No browser, network or screenshot-specific coordinates.

MATCHER_SPEED_1591R10: the same scores as 14.0, computed faster.
  * shape_costs compares one rotated candidate with every reference in a single
    matrix product instead of a Python loop over references and pixels;
  * match_symbols thins each candidate mask once and reuses the skeleton for the
    native and the affine descriptor.
Thresholds, descriptors, rotation steps and the assignment logic are unchanged.
"""
from dataclasses import dataclass
import cv2
cv2.setNumThreads(1)
import numpy as np

MATCHER_VERSION = '14.1'
MAX_SHAPE_COST = 2.0
MIN_MATCH_MARGIN = .25

@dataclass
class Candidate:
    bounds: tuple
    mask: np.ndarray

@dataclass
class Match:
    candidate: object = None
    distance: float = float('inf')
    margin: float = 0.
    reason: str = 'not_found'
    # Diagnostic proposals are never used by click_plan.
    proposed: object = None
    alternative: object = None


def overlaps(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    return min(ax+aw,bx+bw)>max(ax,bx) and min(ay+ah,by+bh)>max(ay,by)


def compact(mask, size=64):
    # MATCHER_SPEED_1591R10: boundingRect/countNonZero give the same crop as np.where.
    binary=np.ascontiguousarray((mask>0).view(np.uint8)) if mask.dtype==np.bool_ else np.ascontiguousarray(mask)
    if cv2.countNonZero(binary)<5:return np.zeros((size,size),np.uint8)
    x,y,w0,h0=cv2.boundingRect(binary)
    crop=mask[y:y+h0,x:x+w0]
    factor=(size-16)/max(crop.shape)
    w,h=max(1,round(crop.shape[1]*factor)),max(1,round(crop.shape[0]*factor))
    tile=cv2.resize(crop,(w,h),interpolation=cv2.INTER_NEAREST)
    out=np.zeros((size,size),np.uint8);out[(size-h)//2:(size-h)//2+h,(size-w)//2:(size-w)//2+w]=tile
    return out


def _thinning_tables():
    """Zhang-Suen erase decision for each of the 256 neighbourhood codes.

    Bit i of the code is neighbour i in the 14.0 order (N, NE, E, SE, S, SW, W, NW).
    The tables reproduce the 14.0 conditions exactly: 2..6 neighbours, one 0->1
    transition around the ring and the phase-specific corner conditions.
    """
    tables = np.zeros((2, 256), dtype=bool)
    for code in range(256):
        n = [(code >> i) & 1 for i in range(8)]
        count = sum(n)
        transitions = sum(1 for i in range(8) if n[i] == 0 and n[(i + 1) % 8] == 1)
        extra0 = (n[0] * n[2] * n[4] == 0) and (n[2] * n[4] * n[6] == 0)
        extra1 = (n[0] * n[2] * n[6] == 0) and (n[0] * n[4] * n[6] == 0)
        base = 2 <= count <= 6 and transitions == 1
        tables[0, code] = base and extra0
        tables[1, code] = base and extra1
    return tables


_THINNING_TABLES = _thinning_tables()
_NEIGHBOUR_WEIGHTS = np.array([1, 2, 4, 8, 16, 32, 64, 128], dtype=np.uint8)


def thin(mask):
    """14.0 skeleton, same iterations and same pixels; MATCHER_SPEED_1591R10 looks the
    neighbourhood up in a table instead of recomputing the ring per pixel."""
    full=(mask>0).astype(np.uint8)
    limit=max(full.shape[0]+2,full.shape[1]+2)  # the 14.0 iteration bound
    ys,xs=np.nonzero(full)
    if not len(xs):
        return full*255
    # Zero pixels never change and a pixel only sees its 8 neighbours, so the
    # bounding box padded by one row/column yields the same skeleton as the full image.
    y0,y1,x0,x1=ys.min(),ys.max()+1,xs.min(),xs.max()+1
    im=np.pad(full[y0:y1,x0:x1],1)
    code=np.zeros((im.shape[0]-2,im.shape[1]-2),np.uint8)
    for _ in range(limit):
        changed=False
        for phase in (0,1):
            p=im[1:-1,1:-1]
            code[...]=im[:-2,1:-1]
            code+=im[:-2,2:]*_NEIGHBOUR_WEIGHTS[1]
            code+=im[1:-1,2:]*_NEIGHBOUR_WEIGHTS[2]
            code+=im[2:,2:]*_NEIGHBOUR_WEIGHTS[3]
            code+=im[2:,1:-1]*_NEIGHBOUR_WEIGHTS[4]
            code+=im[2:,:-2]*_NEIGHBOUR_WEIGHTS[5]
            code+=im[1:-1,:-2]*_NEIGHBOUR_WEIGHTS[6]
            code+=im[:-2,:-2]*_NEIGHBOUR_WEIGHTS[7]
            erase=(p>0)&_THINNING_TABLES[phase][code]
            if np.any(erase):p[erase]=0;changed=True
        if not changed:break
    out=np.zeros(full.shape,np.uint8)
    out[y0:y1,x0:x1]=im[1:-1,1:-1]
    return out*255


def descriptor(mask):
    # Thin before resizing as well as after resizing (scaled_descriptor).
    # Small source masks can otherwise acquire large staircase branches.
    return compact(thin(mask))


def scaled_descriptor(mask):
    return thin(compact(mask))


def affine_descriptor(mask, skeleton=None):
    """Normalize second moments for moderately stretched symbols.

    Covariance whitening removes anisotropic scale before rotation matching.
    The eigenvalue floor limits the axis ratio to 2.5 for near-line masks.
    `skeleton` may pass a precomputed thin(mask); the result is identical.
    """
    skeleton = thin(mask) if skeleton is None else skeleton
    ys, xs = np.where(skeleton > 0)
    if len(xs) < 5:
        return np.zeros((64, 64), np.uint8)
    points = np.column_stack((xs, ys)).astype(float)
    center = points.mean(axis=0)
    vectors = points - center
    covariance = vectors.T @ vectors / len(vectors)
    values, axes = np.linalg.eigh(covariance)
    values = np.maximum(values, max(1, values.max() / 6.25))
    transform = axes @ np.diag(1 / np.sqrt(values)) @ axes.T
    mapped = vectors @ transform.T
    scale = 44 / max(np.ptp(mapped, axis=0).max(), 1)
    linear = transform * scale
    shift = np.array([31.5, 31.5]) - linear @ center
    matrix = np.column_stack((linear, shift)).astype(np.float32)
    warped = cv2.warpAffine(mask, matrix, (64, 64), flags=cv2.INTER_LINEAR)
    return compact(thin((warped >= 128).astype(np.uint8) * 255))


def reference_variant(mask):
    """Optional opening for attached one-pixel noise; retain the original too."""
    kernel = np.ones((2, 2), np.uint8)
    opened = cv2.dilate(cv2.erode(mask, kernel, anchor=(0, 0)),
                        kernel, anchor=(1, 1))
    if np.count_nonzero(opened) < .7 * np.count_nonzero(mask):
        return mask
    return opened


def shape_costs(ref_desc, candidate_desc):
    """Reuse each rotated candidate and its distance map for all references.

    For one rotated candidate the 14.0 score of reference i was
        .5 * (mean(min(d_rot[ref_i], 8)) + mean(min(d_ref_i[rot], 8)))
        + .8 * (mean(d_rot[ref_i] > 3) + mean(d_ref_i[rot] > 3)),
    minimised over the 36 rotations. Every term is a masked mean, i.e. a sum over
    pixels divided by a pixel count, so all references and all rotations of one
    candidate are obtained at once from two matrix products (MATCHER_SPEED_1591R10).
    The products run in float32 like the 14.0 means, so values agree to ~1e-6;
    the pixel counts are exact integers in float32.
    """
    costs = np.full((len(ref_desc), len(candidate_desc)), np.inf)
    if not len(ref_desc) or not len(candidate_desc):
        return costs
    ref_masks = np.stack([np.asarray(a) > 0 for a in ref_desc])            # (R, 64, 64)
    ref_counts = ref_masks.reshape(len(ref_desc), -1).sum(axis=1)          # (R,)
    ref_valid = ref_counts >= 5
    if not ref_valid.any():
        return costs
    ref_distances = np.stack([cv2.distanceTransform((~a).astype(np.uint8), cv2.DIST_L2, 3)
                              for a in ref_masks])                          # (R, 64, 64)
    masks_t = np.ascontiguousarray(ref_masks.reshape(len(ref_desc), -1).T.astype(np.float32))  # (N, R)
    flat_distances = ref_distances.reshape(len(ref_desc), -1)
    near_ref_t = np.ascontiguousarray(np.minimum(flat_distances, 8).T.astype(np.float32))    # (N, R)
    far_ref_t = np.ascontiguousarray((flat_distances > 3).T.astype(np.float32))              # (N, R)
    safe_counts = np.where(ref_valid, ref_counts, 1).astype(np.float32)
    matrix = {angle: cv2.getRotationMatrix2D((31.5, 31.5), angle, 1) for angle in range(0, 360, 10)}
    for j, b in enumerate(candidate_desc):
        if np.count_nonzero(b) < 5:
            continue
        rotations, distances = [], []
        for angle in range(0, 360, 10):
            rotated = compact(cv2.warpAffine(b, matrix[angle], (64, 64), flags=cv2.INTER_NEAREST))
            if not cv2.countNonZero(rotated):
                continue
            rotations.append(rotated.reshape(-1))
            # Zero pixels are the sources: 255-background/0-shape equals the 14.0 ~mask.
            distances.append(cv2.distanceTransform(cv2.bitwise_not(rotated),
                                                   cv2.DIST_L2, 3).reshape(-1))
        if not rotations:
            continue
        rotated_pixels = (np.stack(rotations) > 0).astype(np.float32)        # (A, N)
        rotated_distance = np.stack(distances)                               # (A, N) float32
        rotated_counts = rotated_pixels.sum(axis=1)[:, None]                 # (A, 1)
        # d_rot sampled at reference pixels, averaged per reference.
        near_a = (np.minimum(rotated_distance, 8) @ masks_t) / safe_counts
        far_a = ((rotated_distance > 3).astype(np.float32) @ masks_t) / safe_counts
        # d_ref sampled at rotated pixels, averaged per rotation.
        near_b = (rotated_pixels @ near_ref_t) / rotated_counts
        far_b = (rotated_pixels @ far_ref_t) / rotated_counts
        value = .5 * (near_a + near_b) + .8 * (far_a + far_b)                # (A, R)
        best = value.min(axis=0)
        costs[ref_valid, j] = best[ref_valid]
    return costs


def pair_cost(a, b):
    return float(shape_costs([a], [b])[0, 0])


def hue_centers(hsv):
    ok=(hsv[:,:,1]>=140)&(hsv[:,:,2]>=100)
    hist=np.bincount(hsv[:,:,0][ok],minlength=180)
    smoothed=np.array([sum(hist[np.arange(i-8,i+9)%180]) for i in range(180)])
    centers=[]
    for i in np.argsort(smoothed)[::-1]:
        if smoothed[i]<max(20,.03*smoothed.max()):continue
        if all(min(abs(int(i)-j),180-abs(int(i)-j))>25 for j in centers):centers.append(int(i))
        if len(centers)==3:break
    return centers


def regions(mask, radius):
    # Dilation is only a grouping map: preserve original stroke pixels.
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1))
    group=cv2.dilate(mask,kernel)
    count,labels,stats,_=cv2.connectedComponentsWithStats(group)
    height,width=mask.shape
    out=[]
    for k in range(1,count):
        x,y,w,h,_=map(int,stats[k])
        part=np.where(labels[y:y+h,x:x+w]==k,mask[y:y+h,x:x+w],0)
        ys,xs=np.where(part>0)
        if len(xs)<20:continue
        x0,y0=int(xs.min()),int(ys.min());ww,hh=int(xs.max()-x0+1),int(ys.max()-y0+1)
        box=(x+x0,y+y0,ww,hh)
        if min(ww,hh)<max(8,height*.045) or ww>width*.28 or hh>height*.45:continue
        if max(ww,hh)/min(ww,hh)>3.5:continue
        if box[0]<=1 or box[1]<=1 or box[0]+ww>=width-1 or box[1]+hh>=height-1:continue
        out.append(Candidate(box,part[y0:y0+hh,x0:x0+ww].copy()))
    return out


def families(picture):
    hsv=cv2.cvtColor(picture,cv2.COLOR_BGR2HSV)
    hue=hsv[:,:,0].astype(np.int16)
    # MATCHER_SPEED_1591R10: neighbouring thresholds often yield the very same mask;
    # regions() is deterministic in (mask, radius), so its result is reused verbatim.
    memo={}
    def regions_cached(mask,radius):
        key=(mask.tobytes(),radius)
        if key not in memo:
            memo[key]=regions(mask,radius) if cv2.countNonZero(mask)>=20 else []
        return memo[key]
    for center in hue_centers(hsv):
        delta=np.abs(hue-center);delta=np.minimum(delta,180-delta)
        pool={}
        for width in (24,42):
            for saturation in (80,130,180,220,245):
                for value in (90,150,190,230,250):
                    if value>190 and saturation<180:continue
                    mask=((delta<=width)&(hsv[:,:,1]>=saturation)&(hsv[:,:,2]>=value)).astype(np.uint8)*255
                    for radius in (1,3,6):
                        for c in regions_cached(mask,radius):pool[(c.bounds,c.mask.tobytes())]=c
        # A broad hue interval can join a green stroke to a yellow background.
        # Narrow, shifted intervals recover local strokes of the same palette.
        for shift in (-12, 0, 12):
            local = np.abs(hue - ((center + shift) % 180))
            local = np.minimum(local, 180-local)
            for width in (8, 14):
                for saturation, value in ((130,150),(180,190),(220,230),(245,250)):
                    mask=((local<=width)&(hsv[:,:,1]>=saturation)&(hsv[:,:,2]>=value)).astype(np.uint8)*255
                    for radius in (1,3,6):
                        for c in regions_cached(mask,radius):pool[(c.bounds,c.mask.tobytes())]=c
        yield center,list(pool.values())


def partial_assignment(costs,candidates,max_cost=MAX_SHAPE_COST,min_margin=MIN_MATCH_MARGIN):
    # Per-reference independent acceptance. Unrecognised rows do not consume
    # an object and cannot push a good row onto its second-choice object.
    costs=np.asarray(costs,dtype=float)
    if costs.ndim!=2 or costs.shape[1]!=len(candidates):
        raise ValueError('Несовместимые размеры матрицы сравнения и списка фигур.')
    costs=np.where(np.isfinite(costs),costs,np.inf)
    result=[]
    for row in costs:
        if not np.any(np.isfinite(row)):
            result.append(Match())
            continue
        ordered=np.argsort(row);chosen=[]
        for j in ordered:
            if any(overlaps(candidates[j].bounds,candidates[k].bounds) for k in chosen):continue
            chosen.append(int(j))
            if len(chosen)==2:break
        if not chosen:
            result.append(Match());continue
        j=chosen[0];score=float(row[j]);gap=float(row[chosen[1]]-score) if len(chosen)>1 else float('inf')
        proposed=candidates[j]
        alternative=candidates[chosen[1]] if len(chosen)>1 else None
        if score>max_cost:result.append(Match(None,score,gap,'weak_shape',proposed,alternative))
        elif gap<min_margin:result.append(Match(None,score,gap,'ambiguous',proposed,alternative))
        else:result.append(Match(proposed,score,gap,'matched',proposed,alternative))
    # Keep only a clearly stronger row when two rows claim the same object.
    # Close scores reject both. A rejected row never consumes a second object.
    conflicts=set()
    for i,a in enumerate(result):
        if a.candidate is None:continue
        for j in range(i+1,len(result)):
            b=result[j]
            if b.candidate is None or not overlaps(a.candidate.bounds,b.candidate.bounds):
                continue
            if abs(a.distance-b.distance)<min_margin:
                conflicts.update((i,j))
            else:
                conflicts.add(i if a.distance>b.distance else j)
    for i in conflicts:
        m=result[i]
        result[i]=Match(None,m.distance,m.margin,'conflict',m.proposed,m.alternative)
    return result


def complete_assignment(costs, candidates, max_cost=MAX_SHAPE_COST,
                        min_margin=MIN_MATCH_MARGIN):
    """Resolve a complete, distinct set without forcing missing shapes.

    Independent matches remain anchors. A joint solution is used only when
    every row is below the shape threshold, every assignment has a sufficient
    global margin, and all anchors retain the same spatial object. Otherwise
    return the independent partial result, including its unknowns.
    """
    partial = partial_assignment(costs, candidates, max_cost, min_margin)
    if all(match.candidate is not None for match in partial):
        return partial
    costs = np.asarray(costs, dtype=float)
    options = []
    for row in costs:
        choices = []
        for index in np.argsort(row):
            if not np.isfinite(row[index]) or row[index] > max_cost:
                break
            if any(overlaps(candidates[index].bounds, candidates[j].bounds)
                   for _, j in choices):
                continue
            choices.append((float(row[index]), int(index)))
        if not choices:
            return partial
        # Keep missing-object and ambiguity thresholds independent.
        choices.append((max_cost + min_margin, -1))
        options.append(choices)
    order = sorted(range(len(options)), key=lambda i: len(options[i]))

    def solve(forbidden=None):
        rows = []
        for i in order:
            rows.append([(value, j) for value, j in options[i]
                         if forbidden is None or i != forbidden[0] or j < 0
                         or not overlaps(candidates[j].bounds, forbidden[1])])
        lower = np.r_[np.cumsum([row[0][0] for row in rows][::-1])[::-1], 0.]
        best = sum(row[-1][0] for row in rows) + 1e-8
        answer = [-1] * len(options)

        def search(depth, total, occupied, selected):
            nonlocal best, answer
            if total + lower[depth] >= best:
                return
            if depth == len(order):
                best, answer = total, selected.copy()
                return
            for value, j in rows[depth]:
                if total + value + lower[depth + 1] >= best:
                    continue
                if j >= 0 and any(overlaps(candidates[j].bounds, candidates[k].bounds)
                                  for k in occupied):
                    continue
                selected[order[depth]] = j
                search(depth + 1, total + value,
                       occupied + [j] if j >= 0 else occupied, selected)

        search(0, 0., [], [-1] * len(options))
        return best, answer

    total, selected = solve()
    if any(j < 0 for j in selected):
        return partial
    for match, j in zip(partial, selected):
        if (match.candidate is not None and
                not overlaps(match.candidate.bounds, candidates[j].bounds)):
            return partial
    result = []
    for i, j in enumerate(selected):
        other, alternative = solve((i, candidates[j].bounds))
        gap = other - total
        if gap + 1e-9 < min_margin:
            return partial
        alt = candidates[alternative[i]] if alternative[i] >= 0 else None
        result.append(Match(candidates[j], float(costs[i, j]), float(gap),
                            'matched', candidates[j], alt))
    return result


def best_effort_assignment(costs, candidates):
    """Minimum-cost complete assignment with distinct, non-overlapping boxes.

    There is no confidence cutoff or dummy/unassigned option. Return None only
    when the extracted regions cannot form a complete set with finite scores.
    Equal boxes share a geometry node, retaining the best mask for each row.
    A more expensive containing box is dominated by its cheaper contained box:
    replacing it cannot add a conflict with any other selected region.
    """
    costs = np.asarray(costs, dtype=float)
    if costs.ndim != 2 or costs.shape[1] != len(candidates):
        raise ValueError('Несовместимые размеры матрицы сравнения и списка фигур.')
    count = costs.shape[0]
    if not count:
        return []
    bounds = list(dict.fromkeys(c.bounds for c in candidates))
    if len(bounds) < count:
        return None
    lookup = {box: j for j, box in enumerate(bounds)}
    scores = np.full((count, len(bounds)), np.inf)
    masks = np.full(scores.shape, -1, dtype=int)
    for j, candidate in enumerate(candidates):
        k = lookup[candidate.bounds]
        improve = np.isfinite(costs[:, j]) & (costs[:, j] < scores[:, k])
        scores[improve, k] = costs[improve, j]
        masks[improve, k] = j
    boxes = np.asarray(bounds)
    left, top = boxes[:, 0], boxes[:, 1]
    right, bottom = left + boxes[:, 2], top + boxes[:, 3]
    conflict = ((np.minimum(right[:, None], right) > np.maximum(left[:, None], left))
                & (np.minimum(bottom[:, None], bottom) > np.maximum(top[:, None], top)))
    # contained[a, b]: choosing a uses no more space than choosing b.
    contained = ((left[:, None] >= left) & (top[:, None] >= top)
                 & (right[:, None] <= right) & (bottom[:, None] <= bottom))
    options = []
    for row in scores:
        discarded = np.zeros(len(bounds), dtype=bool)
        choices = []
        for k in np.argsort(row, kind='stable'):
            if not np.isfinite(row[k]):
                break
            if discarded[k]:
                continue
            choices.append(int(k))
            discarded |= contained[k]
        if not choices:
            return None
        options.append(np.asarray(choices, dtype=int))
    best, answer = float('inf'), None
    selected = [-1] * count

    def search(remaining, occupied, total):
        nonlocal best, answer
        if not remaining:
            if total < best:
                best, answer = total, selected.copy()
            return
        available = {i: options[i][~occupied[options[i]]] for i in remaining}
        if any(not len(row) for row in available.values()):
            return
        minima = {i: float(scores[i, row[0]]) for i, row in available.items()}
        lower = total + sum(minima.values())
        if lower >= best:
            return
        # Search the most constrained reference first, but keep its output index.
        i = min(remaining, key=lambda r: len(available[r]))
        rest = tuple(r for r in remaining if r != i)
        for k in available[i]:
            value = float(scores[i, k])
            if lower - minima[i] + value >= best:
                break  # candidates are sorted by cost
            selected[i] = int(k)
            search(rest, occupied | conflict[k], total + value)

    search(tuple(range(count)), np.zeros(len(bounds), dtype=bool), 0.)
    if answer is None:
        return None
    result = []
    for i, k in enumerate(answer):
        candidate = candidates[masks[i, k]]
        other = np.flatnonzero(~conflict[k] & np.isfinite(scores[i]))
        alt = int(other[np.argmin(scores[i, other])]) if len(other) else None
        gap = float(scores[i, alt] - scores[i, k]) if alt is not None else float('inf')
        alternative = candidates[masks[i, alt]] if alt is not None else None
        result.append(Match(candidate, float(scores[i, k]), gap,
                            'best_effort', candidate, alternative))
    return result


def choose_matches(costs, pool, indexed_groups, progress=None):
    """Preserve complete confident solutions; otherwise select a full best guess."""
    best = None
    for _, group in indexed_groups:
        matches = complete_assignment(costs[:, group], [pool[j] for j in group])
        good = sum(m.candidate is not None for m in matches)
        score = (good, -sum(min(3, m.distance) for m in matches))
        if best is None or score > best[0]:
            best = (score, matches)
    if best is not None and all(m.candidate is not None for m in best[1]):
        return best[1]
    if progress:
        progress('Выбор полного набора: сомнительные пары тоже получат вариант…')
    full = []
    for _, group in indexed_groups:
        matches = best_effort_assignment(costs[:, group], [pool[j] for j in group])
        if matches is not None:
            full.append(matches)
    if full:
        return min(full, key=lambda matches: sum(m.distance for m in matches))
    matches = best_effort_assignment(costs, pool)
    if matches is None:
        raise ValueError('Из выделенных областей нельзя составить полный набор '
                         'отдельных фигур. Проверь снимок и границы задания.')
    return matches


def match_symbols(picture, refs, progress=None):
    if not refs:
        return []
    if progress:
        progress('Выделение областей фигур…')
    groups = list(families(picture))
    pool, indices, indexed_groups = [], {}, []
    for center, candidates in groups:
        group = []
        for candidate in candidates:
            key = (candidate.bounds, candidate.mask.tobytes())
            if key not in indices:
                indices[key] = len(pool)
                pool.append(candidate)
            group.append(indices[key])
        if group:
            indexed_groups.append((center, group))
    if not pool:
        raise ValueError('На снимке не выделены области фигур. Проверь границы задания.')
    if progress:
        progress(f'Выделено {len(pool)} вариантов фигур. Сравнение контуров…')

    # Compute every distinct candidate once, even when colour groups overlap.
    if progress:
        progress('Подготовка дескрипторов фигур…')
    # MATCHER_SPEED_1591R10: thin each mask once; descriptor(mask) == compact(thin(mask)).
    skeletons = [thin(c.mask) for c in pool]
    native = [compact(s) for s in skeletons]
    scaled = [scaled_descriptor(c.mask) for c in pool]
    variants = [reference_variant(r) for r in refs]
    if progress: progress('SHAPE_NATIVE_START')
    # MATCHER_SPEED_1591R10: the CLEAN pass compares the same native candidates with the
    # noise-cleaned references, so both reference sets share one rotation sweep.
    # shape_costs rows are independent: the two halves equal two separate calls.
    joined = shape_costs([descriptor(r) for r in refs] + [descriptor(r) for r in variants], native)
    native_costs, clean_costs = joined[:len(refs)], joined[len(refs):]
    if progress: progress('SHAPE_NATIVE_DONE')
    if progress: progress('SHAPE_SCALED_START')
    scaled_costs = shape_costs([scaled_descriptor(r) for r in refs], scaled)
    if progress: progress('SHAPE_SCALED_DONE')
    costs = (native_costs + scaled_costs) * .5
    if progress:
        progress('Проверка образцов с очищенным шумом…')
    if progress: progress('SHAPE_CLEAN_START')
    costs = np.minimum(costs, clean_costs)
    if progress: progress('SHAPE_CLEAN_DONE')
    if progress:
        progress('Проверка растяжения фигур…')
    affine = [affine_descriptor(c.mask, skeleton=s) for c, s in zip(pool, skeletons)]
    if progress: progress('SHAPE_AFFINE_START')
    costs = np.minimum(costs, shape_costs([affine_descriptor(r) for r in variants], affine))
    if progress: progress('SHAPE_AFFINE_DONE')

    if progress:
        progress('Финальное сопоставление фигур…')
    return choose_matches(costs, pool, indexed_groups, progress)
